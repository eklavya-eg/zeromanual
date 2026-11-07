import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.notifications import NotificationStore
from app.routes import notifications as routes


def test_workflow_completion_uses_websocket_history_and_keeps_agent_notifications(monkeypatch):
    if os.getenv("RUN_REDIS_TESTS") != "1":
        pytest.skip("Set RUN_REDIS_TESTS=1 with Redis running")
    store = NotificationStore(namespace=f"test:workflow-notifications:{uuid4().hex}")
    monkeypatch.setattr(routes, "notification_store", store)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            keys = [key async for key in store.client().scan_iter(match=f"{store.namespace}:*")]
            if keys:
                await store.client().delete(*keys)
            await store.close()

    app = FastAPI(lifespan=lifespan)
    app.include_router(routes.router, prefix="/api")
    run = SimpleNamespace(
        id=str(uuid4()), workflow_id=str(uuid4()), status="succeeded", error=None,
        attempt_count=1, started_at=datetime.now(UTC), finished_at=datetime.now(UTC),
    )
    with TestClient(app) as api:
        with api.websocket_connect("/api/notifications/ws") as socket:
            api.portal.call(store.publish_workflow_run, run, "Command workflow")
            message = socket.receive_json()
            assert message["type"] == "notification"
            assert message["data"]["kind"] == "workflow_run"
            assert message["data"]["run_id"] == run.id
            assert message["data"]["workflow_name"] == "Command workflow"
            assert message["data"]["status"] == "succeeded"
            api.portal.call(store.publish_workflow_run, run, "Command workflow")
            history = api.get("/api/notifications")
            assert history.status_code == 200
            assert len(history.json()) == 1
            assert history.json()[0]["run_id"] == run.id
            run.status, run.error, run.attempt_count = "failed", "Command exited with code 2", 2
            api.portal.call(store.publish_workflow_run, run, "Command workflow")
            failure = socket.receive_json()["data"]
            assert failure["status"] == "failed"
            assert failure["attempt_count"] == 2
            assert "code 2" in failure["error"]

            async def create_agent_job():
                return await store.create_job(agent_id="test-agent", agent_name="Browser", payload={"task": "test"})

            job_id, token = api.portal.call(create_agent_job)
            response = api.post("/api/notifications/webhook", json={
                "job_id": job_id, "callback_token": token, "status": "completed",
                "response": {"result": "done"}, "error": None,
            })
            assert response.status_code == 204
            agent = socket.receive_json()["data"]
            assert agent["job_id"] == job_id
            assert agent["agent_name"] == "Browser"
            assert agent["status"] == "completed"
        # History survives socket disconnection/reconnect; workflow output stays in the DB.
        history = api.get("/api/notifications").json()
        assert len(history) == 3
        assert {item.get("kind", "sub_agent") for item in history} == {"workflow_run", "sub_agent"}
