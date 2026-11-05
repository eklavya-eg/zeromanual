import asyncio
from types import SimpleNamespace
from typing import Any, cast

from fastapi import HTTPException
from prisma import Prisma
import pytest

from app.routes import scheduled


class FakeSubAgentActions:
    def __init__(self, agent: object | None) -> None:
        self.agent = agent

    async def find_unique(self, *, where: dict[str, str]) -> object | None:
        return self.agent


class FakeDatabase:
    def __init__(self, agent: object | None) -> None:
        self.subagent = FakeSubAgentActions(agent)


@pytest.mark.parametrize("dispatch_status", ["accepted", "queued"])
def test_trial_invokes_registered_sub_agent(monkeypatch, dispatch_status: str) -> None:
    agent = SimpleNamespace(
        id="agent-1",
        name="Browser Agent",
        invoke_url="http://127.0.0.1:8001/invoke",
        enabled=True,
    )
    received: dict[str, Any] = {}

    class FakeNotificationStore:
        async def create_job(self, **kwargs) -> tuple[str, str]:
            received["job"] = kwargs
            return "job-123", "callback-secret"

        async def remove_job(self, job_id: str) -> None:
            received["removed"] = job_id

    async def fake_invoke(
        url: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        received.update({"url": url, "payload": payload, "timeout": timeout_seconds})
        return {"task_id": "job-123", "status": dispatch_status}

    monkeypatch.setattr(scheduled, "notification_store", FakeNotificationStore())
    monkeypatch.setattr(scheduled, "invoke_sub_agent", fake_invoke)
    result = asyncio.run(
        scheduled.invoke_sub_agent_trial(
            "agent-1",
            {"task": "Read the title"},
            cast(Prisma, FakeDatabase(agent)),
        )
    )

    assert result.status == "queued"
    assert result.task_id == "job-123"
    assert received == {
        "job": {
            "agent_id": "agent-1",
            "agent_name": "Browser Agent",
            "payload": {"task": "Read the title"},
        },
        "url": "http://127.0.0.1:8001/invoke",
        "payload": {
            "task": "Read the title",
            "_eye": {
                "job_id": "job-123",
                "webhook_url": "http://127.0.0.1:8000/api/notifications/webhook",
                "callback_token": "callback-secret",
            },
        },
        "timeout": 15,
    }


def test_trial_rejects_disabled_agent() -> None:
    agent = SimpleNamespace(
        id="agent-1",
        name="Browser Agent",
        invoke_url="http://127.0.0.1:8001/invoke",
        enabled=False,
    )

    try:
        asyncio.run(
            scheduled.invoke_sub_agent_trial(
                "agent-1",
                {},
                cast(Prisma, FakeDatabase(agent)),
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail == "Sub-agent is disabled"
    else:
        raise AssertionError("Expected disabled agent invocation to fail")
