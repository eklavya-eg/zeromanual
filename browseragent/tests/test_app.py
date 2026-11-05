import asyncio
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app import app as app_module

client = TestClient(app_module.app)


class FakeHistory:
    def is_successful(self) -> bool:
        return True

    def final_result(self) -> str:
        return "Example Domain"

    def number_of_steps(self) -> int:
        return 2

    def errors(self) -> list[str | None]:
        return []


class FakeAgent:
    last_task: str | None = None
    last_max_steps: int | None = None
    closed = False
    last_available_file_paths: list[str] | None = None

    def __init__(
        self, task: str, llm: object, browser: object, available_file_paths: list[str] | None = None
    ) -> None:
        FakeAgent.last_task = task
        FakeAgent.last_available_file_paths = available_file_paths

    async def run(self, max_steps: int) -> FakeHistory:
        FakeAgent.last_max_steps = max_steps
        return FakeHistory()

    async def close(self) -> None:
        FakeAgent.closed = True


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "browseragent", "status": "ready"}


def test_invoke_runs_browser_agent(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "Browser", lambda **kwargs: object())
    monkeypatch.setattr(app_module, "Agent", FakeAgent)
    monkeypatch.setattr(
        app_module,
        "create_llm",
        lambda provider, model: (object(), "openrouter", "anthropic/claude-sonnet-4"),
    )

    response = client.post(
        "/invoke",
        json={
            "task": "Read the example page",
            "max_steps": 12,
            "provider": "openrouter",
            "model": "anthropic/claude-sonnet-4",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "result": "Example Domain",
        "steps": 2,
        "errors": [],
        "provider": "openrouter",
        "model": "anthropic/claude-sonnet-4",
    }
    assert FakeAgent.last_task == "Read the example page"
    assert FakeAgent.last_max_steps == 12
    assert FakeAgent.closed is True


def test_invoke_accepts_eye_callback(monkeypatch) -> None:
    accepted_jobs: list[str] = []

    async def fake_execute_and_notify(payload) -> None:
        accepted_jobs.append(payload.eye_callback.job_id)

    monkeypatch.setattr(app_module, "execute_and_notify", fake_execute_and_notify)

    response = client.post(
        "/invoke",
        json={
            "task": "Read the example page",
            "_eye": {
                "job_id": "job-123",
                "webhook_url": "http://127.0.0.1:8000/api/notifications/webhook",
                "callback_token": "secret",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "job-123", "status": "accepted"}
    assert accepted_jobs == ["job-123"]


def test_invoke_rejects_empty_task() -> None:
    response = client.post("/invoke", json={"task": ""})

    assert response.status_code == 422


def test_invoke_rejects_unknown_provider() -> None:
    response = client.post(
        "/invoke",
        json={"task": "Read the example page", "provider": "unknown"},
    )

    assert response.status_code == 422


def test_invoke_reports_missing_provider_configuration(monkeypatch) -> None:
    def fail_to_create_llm(provider, model):
        raise app_module.LlmConfigurationError("OPENAI_API_KEY is required")

    monkeypatch.setattr(app_module, "create_llm", fail_to_create_llm)

    response = client.post("/invoke", json={"task": "Read the example page"})

    assert response.status_code == 503
    assert response.json() == {"detail": "OPENAI_API_KEY is required"}


def test_invoke_accepts_legacy_switch_callback(monkeypatch) -> None:
    accepted = []

    async def fake_execute_and_notify(payload):
        accepted.append(payload.switch_callback.job_id)

    monkeypatch.setattr(app_module, "execute_and_notify", fake_execute_and_notify)
    result = client.post("/invoke", json={
        "task": "Read page",
        "_switch": {
            "job_id": "legacy-job",
            "webhook_url": "http://test/callback",
            "callback_token": "secret",
        },
    })
    assert result.json() == {"task_id": "legacy-job", "status": "accepted"}
    assert accepted == ["legacy-job"]


def test_one_shot_preserves_null_result_and_does_not_create_a_session(monkeypatch) -> None:
    async def fake_execute(payload):
        return app_module.InvokeResponse(
            status="failed", result=None, steps=0, errors=[None], provider="openai", model="test",
        )

    monkeypatch.setattr(app_module, "execute", fake_execute)
    result = client.post("/invoke", json={"task": "Read page"})
    assert result.status_code == 200
    assert "id" not in result.json()
    assert result.json()["result"] is None


def test_session_redis_failure_returns_service_unavailable(monkeypatch) -> None:
    from redis.exceptions import ConnectionError
    from test_sessions import Harness, MemoryStore

    class OfflineStore(MemoryStore):
        async def get_session(self, session_id):
            raise ConnectionError("Redis offline")

    async def scenario():
        harness = Harness(store=OfflineStore())
        monkeypatch.setattr(app_module.app.state, "sessions", harness.manager, raising=False)
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_module.app), base_url="http://test"
            ) as api:
                result = await api.post("/invoke", json={"id": str(uuid4()), "task": "Read page"})
                assert result.status_code == 503
                assert not harness.created
        finally:
            await harness.manager.close()

    asyncio.run(scenario())


def test_invoke_validates_session_uuid() -> None:
    response = client.post("/invoke", json={"id": "not-a-uuid", "task": "Read page"})
    assert response.status_code == 422


def test_session_api_queues_busy_browser_and_exposes_results(monkeypatch) -> None:
    from test_sessions import Harness, response as make_response

    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()

        async def execute(payload, browser):
            if payload.task == "first":
                started.set()
                await release.wait()
            return make_response(payload.task)

        harness = Harness(execute=execute)
        monkeypatch.setattr(app_module.app.state, "sessions", harness.manager, raising=False)
        session_id = str(uuid4())
        transport = httpx.ASGITransport(app=app_module.app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
                first = asyncio.create_task(api.post("/invoke", json={"id": session_id, "task": "first"}))
                await asyncio.wait_for(started.wait(), 2)
                queued = await api.post("/invoke", json={"id": session_id, "task": "second"})
                assert queued.status_code == 202
                assert queued.json()["id"] == session_id
                assert queued.json()["status"] == "queued"
                instruction_id = queued.json()["task_id"]
                state = await api.get(f"/sessions/{session_id}")
                assert state.json()["status"] == "working"
                assert "owner" not in state.json()
                assert (await api.get(f"/instructions/{instruction_id}")).json()["status"] == "queued"
                release.set()
                completed = await asyncio.wait_for(first, 2)
                assert completed.status_code == 200
                assert completed.json()["id"] == session_id
                runner = harness.manager.sessions[session_id].runner
                if runner is not None:
                    await asyncio.wait_for(runner, 2)
                result = await api.get(f"/instructions/{instruction_id}")
                assert result.json()["status"] == "completed"
                assert result.json()["response"]["result"] == "second"
                assert (await api.get(f"/sessions/{session_id}")).json()["status"] == "idle"
                assert (await api.get(f"/sessions/{uuid4()}")).status_code == 404
                assert (await api.get(f"/instructions/{uuid4()}")).status_code == 404
        finally:
            release.set()
            await harness.manager.close()

    asyncio.run(scenario())


def test_application_lifespan_keeps_browser_between_calls_then_closes_it(monkeypatch) -> None:
    from types import SimpleNamespace
    from test_sessions import Harness

    harness = Harness()
    monkeypatch.setattr(app_module, "SessionStore", lambda url: harness.store)
    monkeypatch.setattr(
        app_module, "SessionBrowsers",
        lambda: SimpleNamespace(create=harness.create, destroy=harness.destroy),
    )
    monkeypatch.setattr(app_module, "Agent", FakeAgent)
    monkeypatch.setattr(app_module, "create_llm", lambda provider, model: (object(), "openai", "test"))
    session_id = str(uuid4())
    with TestClient(app_module.app) as api:
        resume_path = r"W:\ZeroManual\workers\output\run-1\resume-uuid\resume.pdf"
        for instruction, files in [
            ("Open page", []),
            ("Continue on that page", [resume_path]),
            ("Read confirmation", []),
        ]:
            result = api.post("/invoke", json={
                "id": session_id, "task": instruction, "available_file_paths": files,
            })
            assert result.status_code == 200
            assert result.json()["id"] == session_id
            assert FakeAgent.last_available_file_paths == files
        assert len(harness.created) == 1
        assert not harness.created[0].closed
    assert harness.created[0].closed
    assert not harness.store.metadata


def test_session_api_preserves_webhook_job_id(monkeypatch) -> None:
    from test_sessions import Harness

    async def scenario():
        harness = Harness()
        monkeypatch.setattr(app_module.app.state, "sessions", harness.manager, raising=False)
        session_id = str(uuid4())
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_module.app), base_url="http://test"
            ) as api:
                accepted = await api.post("/invoke", json={
                    "id": session_id,
                    "task": "Read page",
                    "_eye": {
                        "job_id": "external-job-123",
                        "webhook_url": "http://test/callback",
                        "callback_token": "secret",
                    },
                })
                assert accepted.status_code == 202
                assert accepted.json()["task_id"] == "external-job-123"
                assert accepted.json()["instruction_id"]
                runner = harness.manager.sessions[session_id].runner
                if runner is not None:
                    await asyncio.wait_for(runner, 2)
                assert harness.notifications[0][0] == "Read page"
                assert str(harness.notifications[0][1].id) == session_id
        finally:
            await harness.manager.close()

    asyncio.run(scenario())
