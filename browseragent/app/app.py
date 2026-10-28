import os
from typing import Annotated

from browser_use import Agent
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.llm import LlmConfigurationError, LlmProvider, create_llm

app = FastAPI(
    title="Browser Agent",
    description="Detachable browser-use agent service for Switch workflows.",
    root_path=os.getenv("BROWSER_AGENT_ROOT_PATH", ""),
)


class InvokePayload(BaseModel):
    task: Annotated[str, Field(min_length=1, max_length=20_000)]
    max_steps: Annotated[int, Field(ge=1, le=500)] = 100
    provider: LlmProvider | None = None
    model: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class InvokeResponse(BaseModel):
    status: str
    result: str | None
    steps: int
    errors: list[str | None]
    provider: LlmProvider
    model: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"service": "browseragent", "status": "ready"}


@app.post("/invoke", response_model=InvokeResponse)
async def invoke(payload: InvokePayload) -> InvokeResponse:
    try:
        llm, provider, model = create_llm(payload.provider, payload.model)
    except LlmConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    agent = Agent(task=payload.task, llm=llm)
    try:
        history = await agent.run(max_steps=payload.max_steps)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Browser agent execution failed") from exc
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
