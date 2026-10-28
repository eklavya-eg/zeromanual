from typing import Any

import httpx
from prisma import Prisma
from prisma.errors import UniqueViolationError
from prisma.models import WorkflowRun

from app.models import utc_now
from app.schedule_engine import DueOccurrence


class WorkflowExecutionError(RuntimeError):
    pass


async def invoke_sub_agent(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError:
            return {"text": response.text}
        return result if isinstance(result, dict) else {"data": result}


async def _claim_run(
    db: Prisma,
    workflow_id: str,
    schedule_id: str | None,
    occurrence: DueOccurrence | None,
) -> tuple[WorkflowRun, bool]:
    if schedule_id is not None and occurrence is not None:
        existing = await db.workflowrun.find_first(
            where={
                "schedule_id": schedule_id,
                "occurrence_key": occurrence.key,
            }
        )
        if existing is not None:
            if existing.status in {"running", "succeeded"}:
                return existing, False
            retried = await db.workflowrun.update(
                where={"id": existing.id},
                data={
                    "status": "running",
                    "attempt_count": {"increment": 1},
                    "started_at": utc_now(),
                    "finished_at": None,
                    "error": None,
                },
            )
            return retried, True

    data = {
        "workflow_id": workflow_id,
        "schedule_id": schedule_id,
        "occurrence_key": occurrence.key if occurrence else None,
        "scheduled_for": occurrence.scheduled_for.astimezone() if occurrence else None,
        "status": "running",
    }
    try:
        return await db.workflowrun.create(data=data), True
    except UniqueViolationError:
        existing = await db.workflowrun.find_first(
            where={
                "schedule_id": schedule_id,
                "occurrence_key": occurrence.key if occurrence else None,
            }
        )
        if existing is None:
            raise
        return existing, False


async def execute_workflow(
    db: Prisma,
    workflow_id: str,
    schedule_id: str | None = None,
    occurrence: DueOccurrence | None = None,
) -> WorkflowRun:
    workflow = await db.workflow.find_unique(where={"id": workflow_id})
    if workflow is None:
        raise WorkflowExecutionError("Workflow not found")
    if not workflow.enabled:
        raise WorkflowExecutionError("Workflow is disabled")

    run, should_execute = await _claim_run(db, workflow_id, schedule_id, occurrence)
    if not should_execute:
        return run

    steps = await db.workflowstep.find_many(
        where={"workflow_id": workflow_id},
        include={"sub_agent": True},
        order={"position": "asc"},
    )

    try:
        if not steps:
            raise WorkflowExecutionError("Workflow has no steps")

        for step in steps:
            sub_agent = step.sub_agent
            if sub_agent is None:
                raise WorkflowExecutionError(f"Sub-agent for step {step.position} is missing")
            if not sub_agent.enabled:
                raise WorkflowExecutionError(f"Sub-agent '{sub_agent.name}' is disabled")

            step_run = await db.steprun.create(
                data={
                    "workflow_run_id": run.id,
                    "workflow_step_id": step.id,
                    "attempt_number": run.attempt_count,
                    "status": "running",
                }
            )
            try:
                response = await invoke_sub_agent(sub_agent.invoke_url, step.payload)
                await db.steprun.update(
                    where={"id": step_run.id},
                    data={
                        "status": "succeeded",
                        "response": response,
                        "finished_at": utc_now(),
                    },
                )
            except Exception as exc:
                await db.steprun.update(
                    where={"id": step_run.id},
                    data={
                        "status": "failed",
                        "error": str(exc)[:4_000],
                        "finished_at": utc_now(),
                    },
                )
                raise WorkflowExecutionError(
                    f"Step {step.position} ({sub_agent.name}) failed"
                ) from exc

        return await db.workflowrun.update(
            where={"id": run.id},
            data={"status": "succeeded", "finished_at": utc_now()},
        )
    except Exception as exc:
        await db.workflowrun.update(
            where={"id": run.id},
            data={
                "status": "failed",
                "error": str(exc)[:4_000],
                "finished_at": utc_now(),
            },
        )
        if isinstance(exc, WorkflowExecutionError):
            raise
        raise WorkflowExecutionError("Workflow execution failed") from exc
