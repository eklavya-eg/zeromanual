import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from redis.exceptions import ConnectionError

from app import execution
from app.commands import CommandExecutionError
from app.database import get_database
from app.routes.scheduled import router
from app.workflow_runs import WorkflowRunManager


class FakeDatabase:
    def __init__(self, *, enabled=True):
        self.workflow_id = str(uuid4())
        self.run = None
        self.step_run = None
        self.workflow = SimpleNamespace(find_unique=AsyncMock(return_value=SimpleNamespace(
            id=self.workflow_id, name="Test command", enabled=enabled,
        )))
        self.workflowrun = SimpleNamespace(
            create=AsyncMock(side_effect=self.create_run),
            update=AsyncMock(side_effect=self.update_run),
            find_unique=AsyncMock(side_effect=lambda **kwargs: self.run),
        )
        self.workflowstep = SimpleNamespace(find_many=AsyncMock(return_value=[SimpleNamespace(
            id=str(uuid4()), position=1, step_type="command", command="echo test", working_directory=None,
            timeout_seconds=600,
        )]))
        self.steprun = SimpleNamespace(
            create=AsyncMock(side_effect=self.create_step),
            update=AsyncMock(side_effect=self.update_step),
        )

    async def create_run(self, *, data):
        self.run = SimpleNamespace(
            id=str(uuid4()), attempt_count=1, started_at=datetime.now(UTC), finished_at=None, error=None, **data,
        )
        return self.run

    async def update_run(self, *, where, data):
        self.run = SimpleNamespace(**{**vars(self.run), **data})
        return self.run

    async def create_step(self, *, data):
        self.step_run = SimpleNamespace(id=str(uuid4()), **data)
        return self.step_run

    async def update_step(self, *, where, data):
        self.step_run = SimpleNamespace(**{**vars(self.step_run), **data})
        return self.step_run


def application(db, notifications=None):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_database] = lambda: db
    manager = WorkflowRunManager(notifications or SimpleNamespace(publish_workflow_run=AsyncMock()))
    app.state.workflow_runs = manager
    return app, manager


def test_post_returns_persisted_id_before_command_finishes_and_survives_disconnect(monkeypatch):
    async def scenario():
        db = FakeDatabase()
        app, manager = application(db)
        started, release = asyncio.Event(), asyncio.Event()

        async def command(*args):
            started.set()
            await release.wait()
            return {"stdout": "finished", "exit_code": 0}

        monkeypatch.setattr(execution, "execute_command", command)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
                accepted = await asyncio.wait_for(api.post(f"/api/scheduled/run/{db.workflow_id}"), 1)
                assert accepted.status_code == 202
                assert accepted.json()["id"] == db.run.id
                assert accepted.json()["status"] == "running"
                assert accepted.headers["location"] == f"/api/scheduled/runs/{db.run.id}"
                await asyncio.wait_for(started.wait(), 1)
                assert (await api.get(accepted.headers["location"])).json()["status"] == "running"
                assert not manager.notifications.publish_workflow_run.called
            # The HTTP client is gone; the already accepted job still completes.
            release.set()
            await asyncio.wait_for(asyncio.gather(*manager.tasks), 1)
            assert db.run.status == "succeeded"
            assert db.step_run.status == "succeeded"
            manager.notifications.publish_workflow_run.assert_awaited_once_with(db.run, "Test command")
        finally:
            release.set()
            await manager.close()

    asyncio.run(scenario())


def test_background_command_failure_is_persisted_and_notified(monkeypatch):
    async def scenario():
        db = FakeDatabase()
        app, manager = application(db)
        error = CommandExecutionError("Command exited with code 7", {"stdout": "partial", "exit_code": 7})
        monkeypatch.setattr(execution, "execute_command", AsyncMock(side_effect=error))
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
                accepted = await api.post(f"/api/scheduled/run/{db.workflow_id}")
                assert accepted.status_code == 202
                await asyncio.wait_for(asyncio.gather(*manager.tasks), 1)
                record = (await api.get(accepted.headers["location"])).json()
                assert record["status"] == "failed"
                assert "code 7" in record["error"]
            assert db.step_run.status == "failed"
            assert db.step_run.response is not None
            manager.notifications.publish_workflow_run.assert_awaited_once_with(db.run, "Test command")
        finally:
            await manager.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("wait_until_started", [False, True])
def test_shutdown_cancels_execution_and_finalizes_run(monkeypatch, wait_until_started):
    async def scenario():
        db = FakeDatabase()
        _, manager = application(db)
        started, stopped = asyncio.Event(), asyncio.Event()

        async def command(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        monkeypatch.setattr(execution, "execute_command", command)
        await manager.submit(db, db.workflow_id)
        if wait_until_started:
            await asyncio.wait_for(started.wait(), 1)
        await asyncio.wait_for(manager.close(), 1)
        assert db.run.status == "failed"
        assert "shutdown" in db.run.error
        assert stopped.is_set()
        assert db.step_run.status == "failed"
        assert not manager.tasks
        manager.notifications.publish_workflow_run.assert_awaited_once()

    asyncio.run(scenario())


@pytest.mark.parametrize("missing", [False, True])
def test_preflight_rejects_missing_or_disabled_workflow_without_creating_task(missing):
    async def scenario():
        db = FakeDatabase(enabled=False)
        if missing:
            db.workflow.find_unique.return_value = None
        app, manager = application(db)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
                response = await api.post(f"/api/scheduled/run/{db.workflow_id}")
                assert response.status_code == (404 if missing else 409)
            assert not manager.tasks
            db.workflowrun.create.assert_not_called()
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_step_loading_error_finalizes_already_created_run(monkeypatch):
    async def scenario():
        db = FakeDatabase()
        db.workflowstep.find_many.side_effect = RuntimeError("Could not load steps")
        _, manager = application(db)
        try:
            await manager.submit(db, db.workflow_id)
            await asyncio.gather(*manager.tasks)
            assert db.run.status == "failed"
            assert "Could not load steps" in db.run.error
            manager.notifications.publish_workflow_run.assert_awaited_once()
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_notification_failure_does_not_change_success_or_rerun_command(monkeypatch):
    async def scenario():
        db = FakeDatabase()
        notifications = SimpleNamespace(publish_workflow_run=AsyncMock(side_effect=ConnectionError("Redis offline")))
        _, manager = application(db, notifications)
        command = AsyncMock(return_value={"stdout": "done", "exit_code": 0})
        monkeypatch.setattr(execution, "execute_command", command)
        try:
            await manager.submit(db, db.workflow_id)
            await asyncio.wait_for(asyncio.gather(*manager.tasks), 5)
            assert db.run.status == "succeeded"
            assert notifications.publish_workflow_run.await_count == 3
            command.assert_awaited_once()
        finally:
            await manager.close()

    asyncio.run(scenario())
