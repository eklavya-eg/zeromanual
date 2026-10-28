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

    def __init__(self, task: str, llm: object) -> None:
        FakeAgent.last_task = task

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
