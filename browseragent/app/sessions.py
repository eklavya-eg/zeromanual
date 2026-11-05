import asyncio
import logging
import random
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from time import monotonic
from typing import Any
from uuid import uuid4

from browser_use import Browser

from app.schemas import InvokePayload, InvokeResponse
from app.session_store import SessionStore

logger = logging.getLogger(__name__)


class SessionConflictError(RuntimeError):
    pass


class SessionCapacityError(RuntimeError):
    pass


@dataclass
class Instruction:
    task_id: str
    payload: InvokePayload
    future: asyncio.Future[InvokeResponse]
    queued: bool


@dataclass
class BrowserSession:
    id: str
    owner: str
    ttl: int
    browser: Browser | None = None
    queue: deque[Instruction] = field(default_factory=deque)
    active: Instruction | None = None
    runner: asyncio.Task[None] | None = None
    touched_at: float = field(default_factory=monotonic)

    def metadata(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner": self.owner,
            "status": "working" if self.active or self.queue else "idle",
            "queued_instructions": len(self.queue),
            "ttl_seconds": self.ttl,
        }


class BrowserSessionManager:
    def __init__(
        self,
        store: SessionStore,
        create_browser: Callable[[str], Awaitable[Browser]],
        destroy_browser: Callable[[str, Browser | None], Awaitable[None]],
        execute: Callable[[InvokePayload, Browser], Awaitable[InvokeResponse]],
        notify: Callable[[InvokePayload, InvokeResponse | None, Exception | None], Awaitable[None]],
        *,
        max_sessions: int = 8,
        max_queue: int = 100,
        cleanup_interval: float = 30,
    ) -> None:
        self.store = store
        self.create_browser = create_browser
        self.destroy_browser = destroy_browser
        self.execute = execute
        self.notify = notify
        self.max_sessions = max_sessions
        self.max_queue = max_queue
        self.cleanup_interval = cleanup_interval
        self.sessions: dict[str, BrowserSession] = {}
        self.lock = asyncio.Lock()
        self.closed = False
        self.maintenance: asyncio.Task[None] | None = None

    def start(self) -> None:
        self.maintenance = asyncio.create_task(self._maintenance())

    async def _update(self, session: BrowserSession) -> None:
        if not await self.store.update(session.metadata(), session.ttl):
            raise SessionConflictError("Browser session ownership expired or changed")

    async def submit(self, payload: InvokePayload) -> Instruction:
        if payload.id is None:
            raise ValueError("A browser session UUID is required")
        session_id = str(payload.id)
        async with self.lock:
            if self.closed:
                raise SessionConflictError("Browser agent is shutting down")
            metadata = await self.store.get_session(session_id)
            session = self.sessions.get(session_id)
            if session is not None and metadata is None and session.runner is None:
                self.sessions.pop(session_id)
                await self._dispose(session)
                session = None
            if session is None:
                if metadata is not None:
                    raise SessionConflictError(
                        "This browser belongs to another service process. "
                        "Route to its owner or use a new UUID."
                    )
                if len(self.sessions) >= self.max_sessions:
                    raise SessionCapacityError("Maximum live browser sessions reached")
                session = BrowserSession(session_id, str(uuid4()), random.randint(1800, 3600))
                if not await self.store.claim(session.metadata(), session.ttl):
                    raise SessionConflictError("Browser session was claimed by another process")
                self.sessions[session_id] = session
            elif metadata is None or metadata["owner"] != session.owner:
                raise SessionConflictError("Browser session ownership expired or changed")
            if len(session.queue) >= self.max_queue:
                raise SessionCapacityError("Browser instruction queue is full")

            instruction = Instruction(
                task_id=str(uuid4()),
                payload=payload,
                future=asyncio.get_running_loop().create_future(),
                queued=session.runner is not None,
            )
            # Queued callers do not await this future; retrieve failures to avoid warnings.
            instruction.future.add_done_callback(
                lambda future: future.exception() if not future.cancelled() else None
            )
            await self.store.save_instruction(self._record(session, instruction, "queued"), session.ttl)
            session.queue.append(instruction)
            session.touched_at = monotonic()
            try:
                await self._update(session)
            except Exception:
                session.queue.pop()
                raise
            if session.runner is None:
                session.runner = asyncio.create_task(self._drain(session))
            return instruction

    @staticmethod
    def _record(
        session: BrowserSession,
        instruction: Instruction,
        status: str,
        response: InvokeResponse | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": session.id,
            "task_id": instruction.task_id,
            "status": status,
            "response": response.model_dump(mode="json") if response else None,
            "error": error,
        }

    async def _finish_instruction(
        self,
        session: BrowserSession,
        instruction: Instruction,
        response: InvokeResponse | None,
        error: Exception | None,
    ) -> None:
        if response is None and error is None:
            error = RuntimeError("Browser instruction returned no response")
        status = response.status if response is not None and error is None else "failed"
        await self.store.save_instruction(
            self._record(session, instruction, status, response, str(error) if error else None),
            session.ttl,
        )
        try:
            await self.notify(instruction.payload, response, error)
        except Exception:
            logger.exception("Callback delivery failed for browser instruction %s", instruction.task_id)
        if not instruction.future.done():
            if error is not None:
                instruction.future.set_exception(error)
            elif response is not None:
                instruction.future.set_result(response)

    async def _drain(self, session: BrowserSession) -> None:
        try:
            while True:
                async with self.lock:
                    if not session.queue:
                        session.active = None
                        session.touched_at = monotonic()
                        await self._update(session)
                        session.runner = None
                        return
                    instruction = session.queue.popleft()
                    session.active = instruction
                    await self._update(session)
                await self.store.save_instruction(
                    self._record(session, instruction, "running"), session.ttl
                )
                response = None
                error = None
                try:
                    if session.browser is None:
                        session.browser = await self.create_browser(session.id)
                    response = await self.execute(instruction.payload, session.browser)
                    response = response.model_copy(update={"id": instruction.payload.id})
                except Exception as exc:
                    error = exc
                await self._finish_instruction(session, instruction, response, error)
                session.active = None
        except asyncio.CancelledError:
            await self._fail_remaining(session, "Browser session closed")
            if not self.closed:
                async with self.lock:
                    self.sessions.pop(session.id, None)
                    await self._dispose(session)
            raise
        except Exception:
            logger.exception("Browser session runner failed: %s", session.id)
            await self._fail_remaining(session, "Browser session interrupted; check Redis availability")
            async with self.lock:
                self.sessions.pop(session.id, None)
                await self._dispose(session)
        finally:
            session.runner = None

    async def _fail_remaining(self, session: BrowserSession, message: str) -> None:
        pending = ([session.active] if session.active else []) + list(session.queue)
        session.queue.clear()
        session.active = None
        for instruction in pending:
            error = RuntimeError(message)
            try:
                await self._finish_instruction(session, instruction, None, error)
            except Exception:
                logger.exception("Could not record interrupted instruction %s", instruction.task_id)
            finally:
                if not instruction.future.done():
                    instruction.future.set_exception(error)

    async def _dispose(self, session: BrowserSession) -> None:
        try:
            await self.destroy_browser(session.id, session.browser)
        except Exception:
            logger.exception("Could not close browser %s", session.id)
        try:
            await self.store.delete(session.id, session.owner)
        except Exception:
            logger.exception("Could not release browser metadata %s", session.id)

    async def cleanup(self) -> None:
        async with self.lock:
            for session in list(self.sessions.values()):
                if session.runner is not None:
                    try:
                        await self._update(session)
                        for instruction in ([session.active] if session.active else []) + list(session.queue):
                            await self.store.touch_instruction(instruction.task_id, session.ttl)
                    except SessionConflictError:
                        session.runner.cancel()
                    continue
                metadata = await self.store.get_session(session.id)
                if (
                    monotonic() - session.touched_at >= session.ttl
                    or metadata is None
                    or metadata["owner"] != session.owner
                ):
                    self.sessions.pop(session.id, None)
                    await self._dispose(session)

    async def _maintenance(self) -> None:
        while True:
            await asyncio.sleep(self.cleanup_interval)
            try:
                await self.cleanup()
            except Exception:
                logger.exception("Browser session maintenance failed; will retry")

    async def close(self) -> None:
        async with self.lock:
            self.closed = True
            sessions = list(self.sessions.values())
        if self.maintenance is not None:
            self.maintenance.cancel()
            with suppress(asyncio.CancelledError):
                await self.maintenance
        runners = [session.runner for session in sessions if session.runner is not None]
        for runner in runners:
            runner.cancel()
        await asyncio.gather(*runners, return_exceptions=True)
        for session in sessions:
            await self._dispose(session)
        self.sessions.clear()
        await self.store.close()
