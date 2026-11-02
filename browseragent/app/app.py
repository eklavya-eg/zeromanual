import asyncio
import logging
import os
from typing import Annotated

import httpx
from browser_use import Agent, Browser
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from app.llm import LlmConfigurationError, LlmProvider, create_llm

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Browser Agent",
    description="Detachable browser-use agent service for Switch workflows.",
    root_path=os.getenv("BROWSER_AGENT_ROOT_PATH", ""),
)


class SwitchCallback(BaseModel):
    job_id: str
    webhook_url: HttpUrl
    callback_token: str


class InvokePayload(BaseModel):
    task: Annotated[str, Field(min_length=1, max_length=20_000)]
    max_steps: Annotated[int, Field(ge=1, le=500)] = 100
    provider: LlmProvider | None = None
    model: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    switch_callback: SwitchCallback | None = Field(default=None, alias="_switch")


class InvokeAcceptedResponse(BaseModel):
    task_id: str
    status: str = "accepted"


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


async def execute(payload: InvokePayload) -> InvokeResponse:
    llm, provider, model = create_llm(payload.provider, payload.model)
    browser = Browser(
        executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        user_data_dir=r"D:\BroserUse\User Data",
        profile_directory="Profile 1",
    )
    agent = Agent(task=payload.task, llm=llm, browser=browser)
    try:
        history = await agent.run(max_steps=payload.max_steps)
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


async def post_result(
    callback: SwitchCallback,
    *,
    status: str,
    response: dict | None,
    error: str | None,
) -> None:
    body = {
        "job_id": callback.job_id,
        "callback_token": callback.callback_token,
        "status": status,
        "response": response,
        "error": error,
    }
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                result = await client.post(str(callback.webhook_url), json=body)
                result.raise_for_status()
            return
        except Exception:
            if attempt == 2:
                logger.exception("Could not deliver browser-agent result for %s", callback.job_id)
                return
            await asyncio.sleep(2**attempt)


async def execute_and_notify(payload: InvokePayload) -> None:
    callback = payload.switch_callback
    if callback is None:
        return
    try:
        result = await execute(payload)
        await post_result(
            callback,
            status=result.status,
            response=result.model_dump(mode="json"),
            error=None,
        )
    except Exception as exc:
        await post_result(
            callback,
            status="failed",
            response=None,
            error=str(exc)[:4_000] or "Browser agent execution failed",
        )


@app.post("/invoke", response_model=InvokeResponse | InvokeAcceptedResponse)
async def invoke(
    payload: InvokePayload,
    background_tasks: BackgroundTasks,
) -> InvokeResponse | InvokeAcceptedResponse:
    if payload.switch_callback is not None:
        background_tasks.add_task(execute_and_notify, payload)
        return InvokeAcceptedResponse(task_id=payload.switch_callback.job_id)

    try:
        return await execute(payload)
    except LlmConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Browser agent execution failed") from exc
