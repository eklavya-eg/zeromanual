import asyncio
from types import SimpleNamespace
from typing import Any, cast

from fastapi import HTTPException
from prisma import Prisma

from app.routes import scheduled


class FakeSubAgentActions:
    def __init__(self, agent: object | None) -> None:
        self.agent = agent

    async def find_unique(self, *, where: dict[str, str]) -> object | None:
        return self.agent


class FakeDatabase:
    def __init__(self, agent: object | None) -> None:
        self.subagent = FakeSubAgentActions(agent)


def test_trial_invokes_registered_sub_agent(monkeypatch) -> None:
    agent = SimpleNamespace(
        id="agent-1",
        name="Browser Agent",
        invoke_url="http://127.0.0.1:8001/invoke",
        enabled=True,
    )
    received: dict[str, Any] = {}

    async def fake_invoke(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        received.update({"url": url, "payload": payload})
        return {"title": "Example Domain"}

    monkeypatch.setattr(scheduled, "invoke_sub_agent", fake_invoke)
    result = asyncio.run(
        scheduled.invoke_sub_agent_trial(
            "agent-1",
            {"task": "Read the title"},
            cast(Prisma, FakeDatabase(agent)),
        )
    )

    assert result.status == "succeeded"
    assert result.result == {"title": "Example Domain"}
    assert received == {
        "url": "http://127.0.0.1:8001/invoke",
        "payload": {"task": "Read the title"},
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
