import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID
from typing import Any

import httpx
from browser_use import Agent, Browser
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from redis.exceptions import RedisError

from app.browsers import SessionBrowsers
from app.llm import LlmConfigurationError, create_llm
from app.schemas import InvokeAcceptedResponse, InvokePayload, InvokeResponse, SwitchCallback
from app.session_store import SessionStore
from app.sessions import BrowserSessionManager, SessionCapacityError, SessionConflictError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    browsers = SessionBrowsers()
    store = SessionStore(os.getenv("BROWSER_REDIS_URL", "redis://127.0.0.1:6379/3"))
    manager = BrowserSessionManager(
        store, browsers.create, browsers.destroy, execute, notify_instruction,
        max_sessions=int(os.getenv("BROWSER_MAX_SESSIONS", "8")),
        max_queue=int(os.getenv("BROWSER_MAX_QUEUE", "100")),
    )
    application.state.sessions = manager
    manager.start()
    try:
        yield
    finally:
        await manager.close()


app = FastAPI(
    title="Browser Agent",
    description="Detachable browser-use agent service with resumable browser sessions.",
    root_path=os.getenv("BROWSER_AGENT_ROOT_PATH", ""),
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"service": "browseragent", "status": "ready"}


async def execute(payload: InvokePayload, browser: Browser | None = None) -> InvokeResponse:
    llm, provider, model = create_llm(payload.provider, payload.model)
    if browser is None:
        browser = Browser(
            executable_path=os.getenv(
                "BROWSER_EXECUTABLE_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            ),
            user_data_dir=os.getenv("BROWSER_USER_DATA_DIR", r"D:\BroserUse\User Data"),
            profile_directory=os.getenv("BROWSER_PROFILE_DIRECTORY", "Profile 1"),
        )
    agent = Agent(
        task=payload.task, llm=llm, browser=browser, available_file_paths=payload.available_file_paths
    )
    try:
        history = await agent.run(max_steps=payload.max_steps)
    finally:
        await agent.close()

    return InvokeResponse(
        status="completed" if history.is_successful() else "failed",
        result=history.final_result(),
        steps=history.number_of_steps(),
        errors=history.errors(),
        provider=provider,
        model=model,
    )


async def post_result(
    callback: SwitchCallback,
    *,
    status: str,
    response: dict | None,
    error: str | None,
) -> None:
    body = {
        "job_id": callback.job_id,
        "callback_token": callback.callback_token,
        "status": status,
        "response": response,
        "error": error,
    }
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                result = await client.post(str(callback.webhook_url), json=body)
                result.raise_for_status()
            return
        except Exception:
            if attempt == 2:
                logger.exception("Could not deliver browser-agent result for %s", callback.job_id)
                return
            await asyncio.sleep(2**attempt)


async def execute_and_notify(payload: InvokePayload) -> None:
    callback = payload.switch_callback
    if callback is None:
        return
    try:
        result = await execute(payload)
        await post_result(
            callback,
            status=result.status,
            response=result.model_dump(mode="json", exclude_unset=True),
            error=None,
        )
    except Exception as exc:
        await post_result(
            callback,
            status="failed",
            response=None,
            error=str(exc)[:4_000] or "Browser agent execution failed",
        )


async def notify_instruction(
    payload: InvokePayload,
    result: InvokeResponse | None,
    error: Exception | None,
) -> None:
    if payload.switch_callback is None:
        return
    await post_result(
        payload.switch_callback,
        status=result.status if result is not None else "failed",
        response=result.model_dump(mode="json", exclude_unset=True) if result is not None else None,
        error=str(error)[:4_000] if error is not None else None,
    )


@app.post(
    "/invoke",
    response_model=InvokeResponse | InvokeAcceptedResponse,
    response_model_exclude_unset=True,
)
async def invoke(
    payload: InvokePayload,
    background_tasks: BackgroundTasks,
    request: Request,
    response: Response,
) -> InvokeResponse | InvokeAcceptedResponse:
    if payload.id is not None:
        manager: BrowserSessionManager = request.app.state.sessions
        try:
            instruction = await manager.submit(payload)
            if instruction.queued or payload.switch_callback is not None:
                response.status_code = 202
                accepted = InvokeAcceptedResponse(
                    task_id=payload.switch_callback.job_id if payload.switch_callback else instruction.task_id,
                    id=payload.id,
                    status="queued" if instruction.queued else "accepted",
                )
                if payload.switch_callback is not None:
                    accepted.instruction_id = UUID(instruction.task_id)
                return accepted
            return await asyncio.shield(instruction.future)
        except SessionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SessionCapacityError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except (RedisError, LlmConfigurationError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Browser agent execution failed") from exc

    if payload.switch_callback is not None:
        background_tasks.add_task(execute_and_notify, payload)
        return InvokeAcceptedResponse(task_id=payload.switch_callback.job_id, status="accepted")

    try:
        return await execute(payload)
    except LlmConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Browser agent execution failed") from exc


@app.get("/sessions/{session_id}")
async def get_session(session_id: UUID, request: Request) -> dict[str, Any]:
    manager: BrowserSessionManager = request.app.state.sessions
    try:
        metadata = await manager.store.get_session(str(session_id))
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Browser session store unavailable") from exc
    if metadata is None:
        raise HTTPException(status_code=404, detail="Browser session not found or expired")
    return {key: value for key, value in metadata.items() if key != "owner"}


@app.get("/instructions/{task_id}")
async def get_instruction(task_id: UUID, request: Request) -> dict[str, Any]:
    manager: BrowserSessionManager = request.app.state.sessions
    try:
        record = await manager.store.get_instruction(str(task_id))
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Browser session store unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Instruction not found or expired")
    return record
