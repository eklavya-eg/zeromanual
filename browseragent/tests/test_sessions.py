import asyncio
from copy import deepcopy
from uuid import UUID, uuid4

import pytest

from app.schemas import InvokePayload, InvokeResponse
from app.sessions import BrowserSessionManager, SessionCapacityError, SessionConflictError


class MemoryStore:
    def __init__(self) -> None:
        self.metadata = {}
        self.instructions = {}
        self.ttls = {}

    async def get_session(self, session_id):
        return deepcopy(self.metadata.get(session_id))

    async def claim(self, metadata, ttl):
        if metadata["id"] in self.metadata:
            return False
        self.metadata[metadata["id"]] = deepcopy(metadata)
        self.ttls[metadata["id"]] = ttl
        return True

    async def update(self, metadata, ttl):
        current = self.metadata.get(metadata["id"])
        if current is None or current["owner"] != metadata["owner"]:
            return False
        self.metadata[metadata["id"]] = deepcopy(metadata)
        self.ttls[metadata["id"]] = ttl
        return True

    async def delete(self, session_id, owner):
        if self.metadata.get(session_id, {}).get("owner") == owner:
            self.metadata.pop(session_id, None)

    async def purge(self, session_id, owner):
        current = self.metadata.get(session_id)
        if current is not None and current["owner"] != owner:
            return False
        self.metadata.pop(session_id, None)
        self.ttls.pop(session_id, None)
        for task_id, record in list(self.instructions.items()):
            if record.get("id") == session_id:
                self.instructions.pop(task_id)
        return True

    async def save_instruction(self, record, ttl):
        self.instructions[record["task_id"]] = deepcopy(record)

    async def get_instruction(self, task_id):
        return deepcopy(self.instructions.get(task_id))

    async def touch_instruction(self, task_id, ttl):
        pass

    async def close(self):
        pass


class FakeBrowser:
    def __init__(self, session_id):
        self.id = session_id
        self.closed = False


def response(task="done"):
    return InvokeResponse(
        status="completed", result=task, steps=1, errors=[], provider="openai", model="test",
    )


class Harness:
    def __init__(self, execute=None, store=None, **kwargs):
        self.store = store or MemoryStore()
        self.created = []
        self.notifications = []
        self.manager = BrowserSessionManager(
            self.store, self.create, self.destroy, execute or self.execute, self.notify, **kwargs,
        )

    async def create(self, session_id):
        browser = FakeBrowser(session_id)
        self.created.append(browser)
        return browser

    async def destroy(self, session_id, browser):
        if browser:
            browser.closed = True

    async def execute(self, payload, browser):
        assert not browser.closed
        return response(payload.task)

    async def notify(self, payload, result, error):
        self.notifications.append((payload.task, result, error))


async def settle(manager, session_id):
    runner = manager.sessions[session_id].runner
    if runner is not None:
        await asyncio.wait_for(asyncio.shield(runner), 2)


def test_reuses_browser_until_expiry_and_closes_expired_sessions():
    async def scenario():
        harness = Harness()
        manager = harness.manager
        session_id = str(uuid4())
        try:
            for task in ["Open a page", "Read the current page"]:
                instruction = await manager.submit(InvokePayload(id=session_id, task=task))
                result = await asyncio.wait_for(instruction.future, 2)
                assert result.id == UUID(session_id)
                await settle(manager, session_id)
            assert len(harness.created) == 1
            assert not harness.created[0].closed
            metadata = await harness.store.get_session(session_id)
            assert metadata["status"] == "idle"
            assert 1800 <= metadata["ttl_seconds"] <= 3600
            manager.sessions[session_id].touched_at -= metadata["ttl_seconds"] + 1
            await manager.cleanup()
            assert harness.created[0].closed
            assert session_id not in manager.sessions
            assert await harness.store.get_session(session_id) is None
            instruction = await manager.submit(InvokePayload(id=session_id, task="Fresh session"))
            await asyncio.wait_for(instruction.future, 2)
            await settle(manager, session_id)
            assert len(harness.created) == 2
        finally:
            await manager.close()
        assert all(browser.closed for browser in harness.created)

    asyncio.run(scenario())


@pytest.mark.parametrize("fails", [False, True])
def test_working_browser_refreshes_ttl_then_gets_full_idle_window(monkeypatch, fails):
    clock = [1_000.0]
    monkeypatch.setattr("app.sessions.monotonic", lambda: clock[0])

    class ExpiringStore(MemoryStore):
        def __init__(self):
            super().__init__()
            self.expires_at = {}

        async def get_session(self, session_id):
            if clock[0] >= self.expires_at.get(session_id, float("inf")):
                self.metadata.pop(session_id, None)
            return await super().get_session(session_id)

        async def claim(self, metadata, ttl):
            claimed = await super().claim(metadata, ttl)
            if claimed:
                self.expires_at[metadata["id"]] = clock[0] + ttl
            return claimed

        async def update(self, metadata, ttl):
            if await self.get_session(metadata["id"]) is None:
                return False
            updated = await super().update(metadata, ttl)
            if updated:
                self.expires_at[metadata["id"]] = clock[0] + ttl
            return updated

    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()

        async def execute(payload, browser):
            started.set()
            await release.wait()
            if fails:
                raise ValueError("instruction failed")
            return response()

        store = ExpiringStore()
        harness = Harness(execute=execute, store=store)
        manager = harness.manager
        session_id = str(uuid4())
        try:
            instruction = await manager.submit(InvokePayload(id=session_id, task="long task"))
            await asyncio.wait_for(started.wait(), 2)
            session = manager.sessions[session_id]
            ttl = session.ttl
            original_deadline = store.expires_at[session_id]
            for _ in range(ttl * 2 // 30 + 1):
                clock[0] += 30
                await manager.cleanup()
                assert store.expires_at[session_id] == clock[0] + ttl
            assert clock[0] > original_deadline
            assert not harness.created[0].closed
            assert not instruction.future.done()
            assert (await store.get_session(session_id))["status"] == "working"

            release.set()
            if fails:
                with pytest.raises(ValueError, match="instruction failed"):
                    await asyncio.wait_for(instruction.future, 2)
            else:
                await asyncio.wait_for(instruction.future, 2)
            await settle(manager, session_id)
            idle_start = clock[0]
            assert session.touched_at == idle_start
            assert store.expires_at[session_id] == idle_start + ttl
            assert (await store.get_session(session_id))["status"] == "idle"

            clock[0] += ttl - 1
            await manager.cleanup()
            assert not harness.created[0].closed
            assert store.expires_at[session_id] == idle_start + ttl
            clock[0] += 2
            await manager.cleanup()
            assert harness.created[0].closed
            assert session_id not in manager.sessions
            assert await store.get_session(session_id) is None
        finally:
            release.set()
            await manager.close()

    asyncio.run(scenario())


def test_busy_browser_queues_in_fifo_and_other_browsers_run_independently():
    async def scenario():
        started = asyncio.Event()
        unblock = asyncio.Event()
        order = []

        async def execute(payload, browser):
            order.append(payload.task)
            if payload.task == "first":
                started.set()
                await unblock.wait()
            return response(payload.task)

        harness = Harness(execute=execute)
        manager = harness.manager
        session_id = str(uuid4())
        other_id = str(uuid4())
        try:
            first = await manager.submit(InvokePayload(id=session_id, task="first"))
            await asyncio.wait_for(started.wait(), 2)
            second = await manager.submit(InvokePayload(id=session_id, task="second"))
            third = await manager.submit(InvokePayload(id=session_id, task="third"))
            assert not first.queued
            assert second.queued and third.queued
            metadata = await harness.store.get_session(session_id)
            assert metadata["status"] == "working"
            assert metadata["queued_instructions"] == 2
            await manager.cleanup()
            assert (await harness.store.get_instruction(second.task_id))["status"] == "queued"
            other = await manager.submit(InvokePayload(id=other_id, task="independent"))
            await asyncio.wait_for(other.future, 2)
            assert order == ["first", "independent"]
            unblock.set()
            await asyncio.wait_for(asyncio.gather(first.future, second.future, third.future), 2)
            await settle(manager, session_id)
            assert order == ["first", "independent", "second", "third"]
            assert (await harness.store.get_instruction(third.task_id))["response"]["result"] == "third"
            assert (await harness.store.get_session(session_id))["status"] == "idle"
            assert len(harness.created) == 2
        finally:
            unblock.set()
            await manager.close()

    asyncio.run(scenario())


def test_step_failure_does_not_block_later_instructions():
    async def scenario():
        async def execute(payload, browser):
            if payload.task == "fail":
                raise ValueError("test failure")
            return response()

        harness = Harness(execute=execute)
        session_id = str(uuid4())
        try:
            first = await harness.manager.submit(InvokePayload(id=session_id, task="fail"))
            second = await harness.manager.submit(InvokePayload(id=session_id, task="continue"))
            with pytest.raises(ValueError, match="test failure"):
                await asyncio.wait_for(first.future, 2)
            await asyncio.wait_for(second.future, 2)
            await settle(harness.manager, session_id)
            assert (await harness.store.get_instruction(first.task_id))["status"] == "failed"
            assert len(harness.created) == 1
            assert harness.notifications[0][2] is not None
        finally:
            await harness.manager.close()

    asyncio.run(scenario())


def test_request_cancellation_does_not_cancel_accepted_instruction():
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()

        async def execute(payload, browser):
            started.set()
            await release.wait()
            return response()

        harness = Harness(execute=execute)
        manager = harness.manager
        session_id = str(uuid4())
        try:
            instruction = await manager.submit(InvokePayload(id=session_id, task="continue after disconnect"))

            async def wait_for_request():
                return await asyncio.shield(instruction.future)

            request = asyncio.create_task(wait_for_request())
            await asyncio.wait_for(started.wait(), 2)
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
            assert not instruction.future.cancelled()
            release.set()
            assert (await asyncio.wait_for(instruction.future, 2)).status == "completed"
        finally:
            release.set()
            await manager.close()

    asyncio.run(scenario())


def test_maintenance_never_overwrites_completed_result_while_callback_is_pending():
    async def scenario():
        callback_started = asyncio.Event()
        release = asyncio.Event()
        harness = Harness()
        manager = harness.manager
        session_id = str(uuid4())

        async def notify(payload, result, error):
            callback_started.set()
            await release.wait()

        manager.notify = notify
        try:
            instruction = await manager.submit(InvokePayload(id=session_id, task="complete"))
            await asyncio.wait_for(callback_started.wait(), 2)
            await manager.cleanup()
            record = await harness.store.get_instruction(instruction.task_id)
            assert record["status"] == "completed"
            assert record["response"]["result"] == "complete"
            release.set()
            await asyncio.wait_for(instruction.future, 2)
        finally:
            release.set()
            await manager.close()

    asyncio.run(scenario())


def test_remote_ownership_and_capacity_are_rejected():
    async def scenario():
        harness = Harness(max_sessions=1)
        other = Harness(store=harness.store)
        session_id = str(uuid4())
        try:
            first = await harness.manager.submit(InvokePayload(id=session_id, task="one"))
            await asyncio.wait_for(first.future, 2)
            await settle(harness.manager, session_id)
            with pytest.raises(SessionConflictError):
                await other.manager.submit(InvokePayload(id=session_id, task="wrong owner"))
            with pytest.raises(SessionCapacityError):
                await harness.manager.submit(InvokePayload(id=uuid4(), task="too many"))
        finally:
            await other.manager.close()
            await harness.manager.close()

    asyncio.run(scenario())


def test_expired_redis_metadata_discards_old_browser_before_reuse():
    async def scenario():
        harness = Harness()
        manager = harness.manager
        session_id = str(uuid4())
        try:
            first = await manager.submit(InvokePayload(id=session_id, task="original"))
            await asyncio.wait_for(first.future, 2)
            await settle(manager, session_id)
            harness.store.metadata.pop(session_id)
            second = await manager.submit(InvokePayload(id=session_id, task="new browser"))
            await asyncio.wait_for(second.future, 2)
            await settle(manager, session_id)
            assert harness.created[0].closed
            assert len(harness.created) == 2
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_queue_capacity_and_ownership_loss_do_not_leak_browsers():
    async def scenario():
        started = asyncio.Event()

        async def execute(payload, browser):
            started.set()
            await asyncio.Event().wait()

        harness = Harness(execute=execute, max_queue=1)
        manager = harness.manager
        session_id = str(uuid4())
        try:
            first = await manager.submit(InvokePayload(id=session_id, task="working"))
            await asyncio.wait_for(started.wait(), 2)
            second = await manager.submit(InvokePayload(id=session_id, task="queued"))
            with pytest.raises(SessionCapacityError):
                await manager.submit(InvokePayload(id=session_id, task="overflow"))
            harness.store.metadata[session_id]["owner"] = "new-owner"
            runner = manager.sessions[session_id].runner
            await manager.cleanup()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(runner, 2)
            for instruction in [first, second]:
                with pytest.raises(RuntimeError, match="closed"):
                    await instruction.future
            assert harness.created[0].closed
            assert session_id not in manager.sessions
            assert harness.store.metadata[session_id]["owner"] == "new-owner"
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_shutdown_fails_pending_work_and_releases_browser():
    async def scenario():
        started = asyncio.Event()

        async def execute(payload, browser):
            started.set()
            await asyncio.Event().wait()

        harness = Harness(execute=execute)
        session_id = str(uuid4())
        first = await harness.manager.submit(InvokePayload(id=session_id, task="one"))
        await asyncio.wait_for(started.wait(), 2)
        second = await harness.manager.submit(InvokePayload(id=session_id, task="two"))
        await asyncio.wait_for(harness.manager.close(), 2)
        for instruction in [first, second]:
            with pytest.raises(RuntimeError, match="closed"):
                await instruction.future
            assert (await harness.store.get_instruction(instruction.task_id))["status"] == "failed"
        assert harness.created[0].closed
        assert await harness.store.get_session(session_id) is None

    asyncio.run(scenario())
