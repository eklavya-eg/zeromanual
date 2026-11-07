import asyncio
import os
import time
from datetime import datetime
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prisma import Prisma

from app import execution
from app.database import get_database
from app.routes.scheduled import router
from app.workflow_runs import WorkflowRunManager
from tests.test_commands import python_command

TOKEN = "test-command-token"
HEADERS = {"X-Eye-Command-Token": TOKEN}


class MemoryNotifications:
    def __init__(self):
        self.completed = []

    async def publish_workflow_run(self, run, workflow_name):
        self.completed.append((run, workflow_name))


def wait_for_run(api, run_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = api.get(f"/api/scheduled/runs/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] in {"succeeded", "failed"}:
            return run
        time.sleep(0.05)
    pytest.fail("Workflow did not finish within the test deadline")


@pytest.fixture
def command_client(monkeypatch):
    if os.getenv("RUN_DATABASE_TESTS") != "1":
        pytest.skip("Set RUN_DATABASE_TESTS=1 with PostgreSQL running")
    monkeypatch.setenv("EYE_ENABLE_COMMAND_STEPS", "true")
    monkeypatch.setenv("EYE_COMMAND_ADMIN_TOKEN", TOKEN)
    db = Prisma()

    @asynccontextmanager
    async def lifespan(app):
        await db.connect()
        app.state.workflow_runs = WorkflowRunManager(MemoryNotifications())
        try:
            yield
        finally:
            await app.state.workflow_runs.close()
            await db.disconnect()

    application = FastAPI(lifespan=lifespan)
    application.include_router(router, prefix="/api")
    application.dependency_overrides[get_database] = lambda: db
    # Do not start the production scheduler or execute unrelated real schedules in tests.
    with TestClient(application) as client:
        yield client


def test_mixed_workflow_executes_command_then_agent_and_can_switch_step_type(command_client, monkeypatch, tmp_path):
    api = command_client
    calls = []

    async def fake_invoke(url, payload):
        calls.append(payload)
        return {"agent_result": "done"}

    monkeypatch.setattr(execution, "invoke_sub_agent", fake_invoke)
    agent = api.post("/api/scheduled/sub-agents", json={
        "name": f"command-test-{uuid4().hex}", "invoke_url": "http://example.com/invoke",
    }).json()
    workflow_id = None
    try:
        created = api.post("/api/scheduled/workflows", headers=HEADERS, json={
            "name": "Mixed command integration test",
            "steps": [
                {"step_type": "command", "command": python_command('print("script result")'), "working_directory": str(tmp_path)},
                {"sub_agent_id": agent["id"], "payload": {"task": "next step"}},
            ],
        })
        assert created.status_code == 201, created.text
        workflow = created.json()
        workflow_id = workflow["id"]
        assert workflow["steps"][0]["sub_agent_id"] is None
        assert workflow["steps"][0]["step_type"] == "command"
        assert workflow["steps"][1]["step_type"] == "sub_agent"
        assert workflow["total_sub_agents"] == 1
        assert api.get(f"/api/scheduled/workflows/{workflow_id}").json() == workflow
        run = api.post(f"/api/scheduled/run/{workflow_id}")
        assert run.status_code == 202, run.text
        assert run.json()["status"] == "running"
        assert run.headers["location"] == f"/api/scheduled/runs/{run.json()['id']}"
        assert wait_for_run(api, run.json()["id"])["status"] == "succeeded"
        results = api.get(f"/api/scheduled/runs/{run.json()['id']}/steps").json()
        assert len(results) == 2
        assert "script result" in results[0]["response"]["stdout"]
        assert results[0]["response"]["working_directory"] == str(tmp_path)
        assert results[0]["response"]["exit_code"] == 0
        assert results[1]["response"] == {"agent_result": "done"}
        assert calls == [{"task": "next step"}]
        # Editing existing command workflows cannot bypass token checks by removing steps.
        forbidden = api.patch(f"/api/scheduled/workflows/{workflow_id}", json={"name": "no token"})
        assert forbidden.status_code == 403
        for step in [
            {"sub_agent_id": agent["id"], "payload": {}},
            {"step_type": "command", "command": python_command('print("updated")')},
        ]:
            updated = api.patch(f"/api/scheduled/workflows/{workflow_id}", headers=HEADERS, json={"steps": [step]})
            assert updated.status_code == 200, updated.text
            returned = updated.json()["steps"][0]
            assert returned["step_type"] == step.get("step_type", "sub_agent")
            assert returned["command"] == step.get("command")
            assert returned["sub_agent_id"] == step.get("sub_agent_id")
        accepted = api.post(f"/api/scheduled/run/{workflow_id}")
        assert accepted.status_code == 202
        assert wait_for_run(api, accepted.json()["id"])["status"] == "succeeded"
    finally:
        if workflow_id:
            assert api.delete(f"/api/scheduled/workflows/{workflow_id}").status_code == 204
        assert api.delete(f"/api/scheduled/sub-agents/{agent['id']}").status_code == 204


@pytest.mark.parametrize("failure", ["nonzero", "timeout"])
def test_command_failure_is_stored_and_stops_later_steps(command_client, monkeypatch, failure):
    script = 'import sys; print("partial", flush=True); sys.exit(4)' if failure == "nonzero" else 'import time; print("partial", flush=True); time.sleep(30)'
    created = command_client.post("/api/scheduled/workflows", headers=HEADERS, json={
        "name": f"Command {failure} test",
        "steps": [
            {"step_type": "command", "command": python_command(script), "timeout_seconds": 3 if failure == "timeout" else 10},
            {"step_type": "command", "command": python_command('print("must not run")')},
        ],
    })
    assert created.status_code == 201, created.text
    workflow_id = created.json()["id"]
    try:
        assert created.json()["total_sub_agents"] == 0
        failed_run = command_client.post(f"/api/scheduled/run/{workflow_id}")
        assert failed_run.status_code == 202
        run = wait_for_run(command_client, failed_run.json()["id"])
        assert run["status"] == "failed"
        steps = command_client.get(f"/api/scheduled/runs/{run['id']}/steps").json()
        assert len(steps) == 1
        assert steps[0]["status"] == "failed"
        assert isinstance(steps[0]["response"]["stdout"], str)
        if failure == "nonzero":
            assert "partial" in steps[0]["response"]["stdout"]
        assert steps[0]["response"]["timed_out"] == (failure == "timeout")
    finally:
        assert command_client.delete(f"/api/scheduled/workflows/{workflow_id}").status_code == 204


def test_scheduled_command_runs_only_once_per_occurrence(command_client):
    created = command_client.post("/api/scheduled/workflows", headers=HEADERS, json={
        "name": "Scheduled command test",
        "steps": [{"step_type": "command", "command": python_command('print("scheduled")')}],
    })
    assert created.status_code == 201, created.text
    workflow_id = created.json()["id"]
    try:
        schedule = command_client.post("/api/scheduled/schedules", json={
            "workflow_id": workflow_id,
            "schedule_type": "time",
            "recurrence": "daily",
            "time_of_day": datetime.now().strftime("%H:%M"),
        })
        assert schedule.status_code == 201, schedule.text
        endpoint = f"/api/scheduled/run/{workflow_id}?schedule_id={schedule.json()['id']}"
        first = command_client.post(endpoint)
        second = command_client.post(endpoint)
        assert first.status_code == second.status_code == 202
        assert first.json()["id"] == second.json()["id"]
        assert wait_for_run(command_client, first.json()["id"])["status"] == "succeeded"
        results = command_client.get(f"/api/scheduled/runs/{first.json()['id']}/steps").json()
        assert len(results) == 1
        assert "scheduled" in results[0]["response"]["stdout"]
    finally:
        assert command_client.delete(f"/api/scheduled/workflows/{workflow_id}").status_code == 204


def test_active_background_workflow_cannot_be_deleted_or_have_steps_replaced(command_client, monkeypatch):
    release = asyncio.Event()

    async def command(*args):
        await release.wait()
        return {"stdout": "done", "exit_code": 0}

    monkeypatch.setattr(execution, "execute_command", command)
    created = command_client.post("/api/scheduled/workflows", headers=HEADERS, json={
        "name": "Active workflow guard test",
        "steps": [{"step_type": "command", "command": "echo test"}],
    })
    assert created.status_code == 201
    workflow_id = created.json()["id"]
    accepted = command_client.post(f"/api/scheduled/run/{workflow_id}")
    try:
        assert accepted.status_code == 202
        assert command_client.delete(f"/api/scheduled/workflows/{workflow_id}").status_code == 409
        assert command_client.patch(f"/api/scheduled/workflows/{workflow_id}", headers=HEADERS, json={
            "steps": [{"step_type": "command", "command": "echo changed"}],
        }).status_code == 409
    finally:
        command_client.portal.call(release.set)
        assert wait_for_run(command_client, accepted.json()["id"])["status"] == "succeeded"
        assert command_client.delete(f"/api/scheduled/workflows/{workflow_id}").status_code == 204


def test_command_api_rejects_invalid_inputs_and_unauthorized_authoring(command_client, monkeypatch):
    data = {"name": "Unauthorized command", "steps": [{"step_type": "command", "command": "echo no"}]}
    assert command_client.post("/api/scheduled/workflows", json=data).status_code == 403
    monkeypatch.setenv("EYE_ENABLE_COMMAND_STEPS", "false")
    assert command_client.post("/api/scheduled/workflows", json=data, headers=HEADERS).status_code == 403
    monkeypatch.setenv("EYE_ENABLE_COMMAND_STEPS", "true")
    data["steps"][0]["sub_agent_id"] = str(uuid4())
    assert command_client.post("/api/scheduled/workflows", json=data, headers=HEADERS).status_code == 422
