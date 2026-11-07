import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from redis.exceptions import ConnectionError

from app import app as app_module
from app.schemas import InvokePayload
from app.sessions import SessionConflictError
from test_sessions import Harness, MemoryStore, settle


def test_delete_cleans_real_redis_and_local_browser_profiles(monkeypatch, tmp_path):
    if os.getenv("RUN_REDIS_TESTS") != "1":
        pytest.skip("Set RUN_REDIS_TESTS=1 with Redis running")

    from app import browsers
    from app.session_store import SessionStore

    monkeypatch.setenv("BROWSER_USER_DATA_DIR", str(tmp_path / "no-seed"))
    monkeypatch.setenv("BROWSER_SESSION_DATA_DIR", str(tmp_path / "sessions"))

    class FakeBrowser:
        def __init__(self, **kwargs):
            self.closed = False

        async def start(self):
            pass

        async def kill(self):
            self.closed = True

    monkeypatch.setattr(browsers, "Browser", FakeBrowser)

    async def scenario():
        store = SessionStore(
            os.getenv("BROWSER_REDIS_URL", "redis://127.0.0.1:6379/3"),
            namespace=f"test:browseragent:{uuid4()}",
        )
        harness = Harness(store=store)
        factory = browsers.SessionBrowsers()
        manager = harness.manager
        manager.create_browser = factory.create
        manager.destroy_browser = factory.destroy
        monkeypatch.setattr(app_module.app.state, "sessions", manager, raising=False)
        session_id = str(uuid4())
        started = asyncio.Event()

        async def execute(payload, browser):
            started.set()
            await asyncio.Event().wait()

        try:
            completed = await manager.submit(InvokePayload(id=session_id, task="completed"))
            await asyncio.wait_for(completed.future, 2)
            await settle(manager, session_id)
            browser = manager.sessions[session_id].browser
            profile = factory.profiles[session_id]
            manager.execute = execute
            active = await manager.submit(InvokePayload(id=session_id, task="active"))
            await asyncio.wait_for(started.wait(), 2)
            queued = await manager.submit(InvokePayload(id=session_id, task="queued"))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_module.app), base_url="http://test"
            ) as api:
                result = await asyncio.wait_for(api.delete(f"/sessions/{session_id}"), 5)
                assert result.status_code == 204
                assert (await api.get(f"/sessions/{session_id}")).status_code == 404
                for instruction in [completed, active, queued]:
                    assert (await api.get(f"/instructions/{instruction.task_id}")).status_code == 404
            for instruction in [active, queued]:
                with pytest.raises(RuntimeError, match="Browser session closed"):
                    await instruction.future
            assert browser.closed
            assert not profile.exists()
            assert not factory.profiles
            assert not manager.sessions
            assert not [key async for key in store.redis.scan_iter(match=f"{store.namespace}:*")]
        finally:
            keys = [key async for key in store.redis.scan_iter(match=f"{store.namespace}:*")]
            if keys:
                await store.redis.delete(*keys)
            await manager.close()

    asyncio.run(scenario())


def test_termination_purges_completed_history_and_allows_fresh_session():
    async def scenario():
        harness = Harness()
        manager = harness.manager
        session_id, other_id = str(uuid4()), str(uuid4())
        try:
            history = []
            for task in ["first", "second"]:
                instruction = await manager.submit(InvokePayload(id=session_id, task=task))
                await asyncio.wait_for(instruction.future, 2)
                await settle(manager, session_id)
                history.append(instruction.task_id)
            other = await manager.submit(InvokePayload(id=other_id, task="unrelated"))
            await asyncio.wait_for(other.future, 2)
            await settle(manager, other_id)
            await asyncio.wait_for(manager.terminate(session_id), 2)
            assert harness.created[0].closed
            assert not harness.created[1].closed
            assert session_id not in manager.sessions
            assert await harness.store.get_session(session_id) is None
            for task_id in history:
                assert await harness.store.get_instruction(task_id) is None
            assert await harness.store.get_instruction(other.task_id) is not None
            await manager.terminate(session_id)
            fresh = await manager.submit(InvokePayload(id=session_id, task="fresh"))
            await asyncio.wait_for(fresh.future, 2)
            await settle(manager, session_id)
            assert len(harness.created) == 3
        finally:
            await manager.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("started", [False, True])
def test_termination_cancels_active_and_queued_instructions(started):
    async def scenario():
        executing = asyncio.Event()
        calls = []

        async def execute(payload, browser):
            calls.append(payload.task)
            executing.set()
            await asyncio.Event().wait()

        harness = Harness(execute=execute)
        manager = harness.manager
        session_id = str(uuid4())
        try:
            first = await manager.submit(InvokePayload(id=session_id, task="active"))
            if started:
                await asyncio.wait_for(executing.wait(), 2)
            second = await manager.submit(InvokePayload(id=session_id, task="queued"))
            await asyncio.wait_for(manager.terminate(session_id), 2)
            assert "queued" not in calls
            for instruction in [first, second]:
                with pytest.raises(RuntimeError, match="Browser session closed"):
                    await asyncio.wait_for(instruction.future, 2)
            assert all(browser.closed for browser in harness.created)
            assert not manager.sessions
            assert not harness.store.metadata
            assert not harness.store.instructions
            assert sorted(item[0] for item in harness.notifications) == ["active", "queued"]
            assert all(item[1] is None and item[2] is not None for item in harness.notifications)
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_termination_blocks_reuse_and_survives_disconnected_delete_caller():
    async def scenario():
        harness = Harness()
        manager = harness.manager
        session_id = str(uuid4())
        closing = asyncio.Event()
        release = asyncio.Event()
        destroys = []

        async def destroy(identifier, browser):
            destroys.append(identifier)
            closing.set()
            await release.wait()
            await harness.destroy(identifier, browser)

        manager.destroy_browser = destroy
        try:
            instruction = await manager.submit(InvokePayload(id=session_id, task="first"))
            await asyncio.wait_for(instruction.future, 2)
            await settle(manager, session_id)
            first_delete = asyncio.create_task(manager.terminate(session_id))
            await asyncio.wait_for(closing.wait(), 2)
            first_delete.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first_delete
            second_delete = asyncio.create_task(manager.terminate(session_id))
            with pytest.raises(SessionConflictError, match="closing"):
                await manager.submit(InvokePayload(id=session_id, task="must not run"))
            await manager.cleanup()
            release.set()
            await asyncio.wait_for(second_delete, 2)
            assert destroys == [session_id]
            assert harness.created[0].closed
            assert not manager.sessions
            assert not harness.store.metadata
            assert not harness.store.instructions
        finally:
            release.set()
            await manager.close()

    asyncio.run(scenario())


def test_termination_during_callback_stops_browser_before_notifying_failure():
    async def scenario():
        harness = Harness()
        manager = harness.manager
        session_id = str(uuid4())
        callback_started = asyncio.Event()
        notified = []

        async def notify(payload, result, error):
            if error is None:
                callback_started.set()
                await asyncio.Event().wait()
            assert harness.created[0].closed
            notified.append(payload.task)

        manager.notify = notify
        try:
            instruction = await manager.submit(InvokePayload(id=session_id, task="callback pending"))
            await asyncio.wait_for(callback_started.wait(), 2)
            await asyncio.wait_for(manager.terminate(session_id), 2)
            with pytest.raises(RuntimeError, match="Browser session closed"):
                await instruction.future
            assert notified == ["callback pending"]
            assert not harness.store.instructions
            assert not manager.sessions
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_termination_during_error_cleanup_settles_every_queued_future():
    class InterruptedStore(MemoryStore):
        async def save_instruction(self, record, ttl):
            if record["status"] == "running":
                raise ConnectionError("Execution interrupted")
            await super().save_instruction(record, ttl)

    async def scenario():
        harness = Harness(store=InterruptedStore())
        manager = harness.manager
        session_id = str(uuid4())
        cleanup_started = asyncio.Event()

        async def notify(payload, result, error):
            if "interrupted" in str(error):
                cleanup_started.set()
                await asyncio.Event().wait()
            harness.notifications.append((payload.task, result, error))

        manager.notify = notify
        try:
            first = await manager.submit(InvokePayload(id=session_id, task="first"))
            second = await manager.submit(InvokePayload(id=session_id, task="second"))
            await asyncio.wait_for(cleanup_started.wait(), 2)
            await asyncio.wait_for(manager.terminate(session_id), 2)
            for instruction in [first, second]:
                assert instruction.future.done()
                with pytest.raises(RuntimeError):
                    await instruction.future
            assert sorted(item[0] for item in harness.notifications) == ["first", "second"]
            assert not manager.sessions
            assert not harness.store.instructions
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_termination_removes_orphaned_results_but_preserves_foreign_owner():
    async def scenario():
        harness = Harness()
        session_id = str(uuid4())
        record = {"id": session_id, "task_id": str(uuid4()), "status": "completed"}
        try:
            await harness.store.save_instruction(record, 1800)
            await harness.store.claim({"id": session_id, "owner": "foreign"}, 1800)
            with pytest.raises(SessionConflictError, match="another service process"):
                await harness.manager.terminate(session_id)
            assert await harness.store.get_instruction(record["task_id"]) == record
            assert await harness.store.get_session(session_id) is not None
            harness.store.metadata.pop(session_id)
            await harness.manager.terminate(session_id)
            assert await harness.store.get_instruction(record["task_id"]) is None
        finally:
            await harness.manager.close()

    asyncio.run(scenario())


def test_termination_does_not_delete_replacement_ownership():
    async def scenario():
        harness = Harness()
        manager = harness.manager
        session_id = str(uuid4())
        try:
            instruction = await manager.submit(InvokePayload(id=session_id, task="original"))
            await asyncio.wait_for(instruction.future, 2)
            await settle(manager, session_id)
            harness.store.metadata[session_id]["owner"] = "replacement"
            with pytest.raises(SessionConflictError, match="ownership changed"):
                await manager.terminate(session_id)
            assert harness.created[0].closed
            assert session_id not in manager.sessions
            assert (await harness.store.get_session(session_id))["owner"] == "replacement"
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_redis_failure_still_closes_local_browser_and_deletion_can_be_retried():
    class OfflineStore(MemoryStore):
        offline = True

        async def purge(self, session_id, owner):
            if self.offline:
                raise ConnectionError("Redis offline")
            return await super().purge(session_id, owner)

    async def scenario():
        store = OfflineStore()
        harness = Harness(store=store)
        manager = harness.manager
        session_id = str(uuid4())
        try:
            instruction = await manager.submit(InvokePayload(id=session_id, task="original"))
            await asyncio.wait_for(instruction.future, 2)
            await settle(manager, session_id)
            with pytest.raises(ConnectionError):
                await manager.terminate(session_id)
            assert harness.created[0].closed
            assert manager.sessions[session_id].browser is None
            with pytest.raises(SessionConflictError, match="closing"):
                await manager.submit(InvokePayload(id=session_id, task="must not reopen"))
            store.offline = False
            await manager.terminate(session_id)
            assert not manager.sessions
            assert not store.metadata
            assert not store.instructions
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_browser_close_failure_is_retryable():
    async def scenario():
        harness = Harness()
        manager = harness.manager
        session_id = str(uuid4())

        async def broken_destroy(identifier, browser):
            raise RuntimeError("Browser kill failed")

        try:
            instruction = await manager.submit(InvokePayload(id=session_id, task="original"))
            await asyncio.wait_for(instruction.future, 2)
            await settle(manager, session_id)
            manager.destroy_browser = broken_destroy
            with pytest.raises(RuntimeError, match="Browser kill failed"):
                await manager.terminate(session_id)
            assert not harness.created[0].closed
            assert manager.sessions[session_id].closing
            assert await harness.store.get_session(session_id) is not None
            manager.destroy_browser = harness.destroy
            await manager.terminate(session_id)
            assert harness.created[0].closed
            assert not manager.sessions
            assert not harness.store.metadata
        finally:
            manager.destroy_browser = harness.destroy
            await manager.close()

    asyncio.run(scenario())


def test_delete_api_purges_sessions_instructions_and_validates_uuid(monkeypatch):
    async def scenario():
        harness = Harness()
        session_id = str(uuid4())
        monkeypatch.setattr(app_module.app.state, "sessions", harness.manager, raising=False)
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_module.app), base_url="http://test"
            ) as api:
                instruction = await harness.manager.submit(InvokePayload(id=session_id, task="open"))
                await asyncio.wait_for(instruction.future, 2)
                await settle(harness.manager, session_id)
                result = await api.delete(f"/sessions/{session_id}")
                assert result.status_code == 204
                assert result.content == b""
                assert harness.created[0].closed
                assert (await api.get(f"/sessions/{session_id}")).status_code == 404
                assert (await api.get(f"/instructions/{instruction.task_id}")).status_code == 404
                assert (await api.delete(f"/sessions/{session_id}")).status_code == 204
                assert (await api.delete("/sessions/not-a-uuid")).status_code == 422
        finally:
            await harness.manager.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("failure,status", [(ConnectionError("offline"), 503), (RuntimeError("kill failed"), 500)])
def test_delete_api_reports_cleanup_errors(monkeypatch, failure, status):
    async def scenario():
        harness = Harness()

        async def fail(session_id):
            raise failure

        monkeypatch.setattr(harness.manager, "terminate", fail)
        monkeypatch.setattr(app_module.app.state, "sessions", harness.manager, raising=False)
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_module.app), base_url="http://test"
            ) as api:
                result = await api.delete(f"/sessions/{uuid4()}")
                assert result.status_code == status
                assert "retry deletion" in result.json()["detail"]
        finally:
            await harness.manager.close()

    asyncio.run(scenario())


def test_delete_api_rejects_foreign_browser_ownership(monkeypatch):
    async def scenario():
        harness = Harness()
        session_id = str(uuid4())
        monkeypatch.setattr(app_module.app.state, "sessions", harness.manager, raising=False)
        await harness.store.claim({"id": session_id, "owner": "foreign"}, 1800)
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_module.app), base_url="http://test"
            ) as api:
                result = await api.delete(f"/sessions/{session_id}")
                assert result.status_code == 409
                assert await harness.store.get_session(session_id) is not None
        finally:
            await harness.manager.close()

    asyncio.run(scenario())
