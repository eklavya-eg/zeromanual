from datetime import time
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from prisma import Prisma
from prisma.errors import UniqueViolationError
from prisma.models import Schedule, SubAgent, Workflow, WorkflowRun

from app.database import get_database
from app.execution import WorkflowExecutionError, execute_workflow, invoke_sub_agent
from app.schedule_engine import due_occurrence
from app.scheduler import reconcile_due_schedules
from app.schemas import (
    RunResponse,
    ScheduleCreate,
    ScheduleFields,
    ScheduleResponse,
    ScheduleUpdate,
    SubAgentCreate,
    SubAgentResponse,
    SubAgentTrialResponse,
    SubAgentUpdate,
    WorkflowCreate,
    WorkflowResponse,
    WorkflowStepResponse,
)
from app.windows_scheduler import delete_windows_task, register_windows_task

router = APIRouter(prefix="/scheduled", tags=["scheduled"])


def _stored_time(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value is not None else None


def _response_time(value: str | None) -> time | None:
    return time.fromisoformat(value) if value is not None else None


def _sub_agent_response(sub_agent: SubAgent) -> SubAgentResponse:
    return SubAgentResponse.model_validate(sub_agent)


def _schedule_response(schedule: Schedule) -> ScheduleResponse:
    return ScheduleResponse(
        id=schedule.id,
        workflow_id=schedule.workflow_id,
        schedule_type=schedule.schedule_type,
        recurrence=schedule.recurrence,
        time_of_day=_response_time(schedule.time_of_day),
        range_start=_response_time(schedule.range_start),
        range_end=_response_time(schedule.range_end),
        day_of_month=schedule.day_of_month,
        month=schedule.month,
        run_if_missed=schedule.run_if_missed,
        misfire_grace_minutes=schedule.misfire_grace_minutes,
        enabled=schedule.enabled,
        windows_task_name=schedule.windows_task_name,
        registration_error=schedule.registration_error,
        created_at=schedule.created_at,
        modified_at=schedule.modified_at,
    )


def _run_response(run: WorkflowRun) -> RunResponse:
    return RunResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        schedule_id=run.schedule_id,
        occurrence_key=run.occurrence_key,
        status=run.status,
        attempt_count=run.attempt_count,
        scheduled_for=run.scheduled_for,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
    )


async def _workflow_response(db: Prisma, workflow: Workflow) -> WorkflowResponse:
    steps = await db.workflowstep.find_many(
        where={"workflow_id": workflow.id},
        order={"position": "asc"},
    )
    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        total_sub_agents=workflow.total_sub_agents,
        enabled=workflow.enabled,
        steps=[
            WorkflowStepResponse(
                id=step.id,
                position=step.position,
                sub_agent_id=step.sub_agent_id,
                payload=step.payload,
            )
            for step in steps
        ],
        created_at=workflow.created_at,
        modified_at=workflow.modified_at,
    )


@router.get("")
async def scheduled_root() -> dict[str, str]:
    return {"service": "scheduled", "status": "ready"}


@router.post("/sub-agents", response_model=SubAgentResponse, status_code=status.HTTP_201_CREATED)
async def create_sub_agent(
    payload: SubAgentCreate,
    db: Prisma = Depends(get_database),
) -> SubAgentResponse:
    try:
        sub_agent = await db.subagent.create(
            data={
                "name": payload.name,
                "description": payload.description,
                "invoke_url": str(payload.invoke_url),
                "enabled": payload.enabled,
            }
        )
    except UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail="Sub-agent name already exists") from exc
    return _sub_agent_response(sub_agent)


@router.get("/sub-agents", response_model=list[SubAgentResponse])
async def list_sub_agents(
    db: Prisma = Depends(get_database),
) -> list[SubAgentResponse]:
    agents = await db.subagent.find_many(order={"name": "asc"})
    return [_sub_agent_response(agent) for agent in agents]


@router.patch("/sub-agents/{sub_agent_id}", response_model=SubAgentResponse)
async def update_sub_agent(
    sub_agent_id: str,
    payload: SubAgentUpdate,
    db: Prisma = Depends(get_database),
) -> SubAgentResponse:
    if await db.subagent.find_unique(where={"id": sub_agent_id}) is None:
        raise HTTPException(status_code=404, detail="Sub-agent not found")
    changes = payload.model_dump(exclude_unset=True)
    if "invoke_url" in changes:
        changes["invoke_url"] = str(changes["invoke_url"])
    try:
        sub_agent = await db.subagent.update(
            where={"id": sub_agent_id},
            data=changes,
        )
    except UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail="Sub-agent name already exists") from exc
    return _sub_agent_response(sub_agent)


@router.post(
    "/sub-agents/{sub_agent_id}/invoke",
    response_model=SubAgentTrialResponse,
)
async def invoke_sub_agent_trial(
    sub_agent_id: str,
    payload: dict[str, Any],
    db: Prisma = Depends(get_database),
) -> SubAgentTrialResponse:
    sub_agent = await db.subagent.find_unique(where={"id": sub_agent_id})
    if sub_agent is None:
        raise HTTPException(status_code=404, detail="Sub-agent not found")
    if not sub_agent.enabled:
        raise HTTPException(status_code=409, detail="Sub-agent is disabled")

    started_at = perf_counter()
    try:
        result = await invoke_sub_agent(sub_agent.invoke_url, payload)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Sub-agent invocation failed: {exc}",
        ) from exc

    return SubAgentTrialResponse(
        agent_id=sub_agent.id,
        agent_name=sub_agent.name,
        status="succeeded",
        duration_ms=round((perf_counter() - started_at) * 1_000),
        result=result,
    )


@router.post("/workflows", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: WorkflowCreate,
    db: Prisma = Depends(get_database),
) -> WorkflowResponse:
    requested_agent_ids = {step.sub_agent_id for step in payload.steps}
    existing_agents = await db.subagent.find_many(
        where={"id": {"in": list(requested_agent_ids)}}
    )
    missing = sorted(requested_agent_ids - {agent.id for agent in existing_agents})
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"message": "Unknown sub-agent IDs", "ids": missing},
        )

    async with db.tx() as transaction:
        workflow = await transaction.workflow.create(
            data={
                "name": payload.name,
                "description": payload.description,
                "total_sub_agents": len(payload.steps),
                "enabled": payload.enabled,
            }
        )
        await transaction.workflowstep.create_many(
            data=[
                {
                    "workflow_id": workflow.id,
                    "sub_agent_id": step.sub_agent_id,
                    "position": position,
                    "payload": step.payload,
                }
                for position, step in enumerate(payload.steps, start=1)
            ]
        )
    return await _workflow_response(db, workflow)


@router.get("/workflows", response_model=list[WorkflowResponse])
async def list_workflows(
    db: Prisma = Depends(get_database),
) -> list[WorkflowResponse]:
    workflows = await db.workflow.find_many(order={"created_at": "asc"})
    return [await _workflow_response(db, workflow) for workflow in workflows]


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    db: Prisma = Depends(get_database),
) -> WorkflowResponse:
    workflow = await db.workflow.find_unique(where={"id": workflow_id})
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return await _workflow_response(db, workflow)


async def _save_registration(db: Prisma, schedule: Schedule) -> Schedule:
    registration = await register_windows_task(schedule)
    return await db.schedule.update(
        where={"id": schedule.id},
        data={
            "windows_task_name": registration.task_name,
            "registration_error": registration.error,
        },
    )


@router.post("/schedules", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    payload: ScheduleCreate,
    db: Prisma = Depends(get_database),
) -> ScheduleResponse:
    if await db.workflow.find_unique(where={"id": payload.workflow_id}) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    schedule = await db.schedule.create(
        data={
            "workflow_id": payload.workflow_id,
            "schedule_type": payload.schedule_type.value,
            "recurrence": payload.recurrence.value,
            "time_of_day": _stored_time(payload.time_of_day),
            "range_start": _stored_time(payload.range_start),
            "range_end": _stored_time(payload.range_end),
            "day_of_month": payload.day_of_month,
            "month": payload.month,
            "run_if_missed": payload.run_if_missed,
            "misfire_grace_minutes": payload.misfire_grace_minutes,
            "enabled": payload.enabled,
        }
    )
    if schedule.enabled:
        schedule = await _save_registration(db, schedule)
    return _schedule_response(schedule)


@router.get("/schedules", response_model=list[ScheduleResponse])
async def list_schedules(
    workflow_id: str | None = Query(default=None),
    db: Prisma = Depends(get_database),
) -> list[ScheduleResponse]:
    where = {"workflow_id": workflow_id} if workflow_id is not None else None
    schedules = await db.schedule.find_many(
        where=where,
        order={"created_at": "asc"},
    )
    return [_schedule_response(schedule) for schedule in schedules]


@router.patch("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    payload: ScheduleUpdate,
    db: Prisma = Depends(get_database),
) -> ScheduleResponse:
    schedule = await db.schedule.find_unique(where={"id": schedule_id})
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    old_task_name = schedule.windows_task_name
    current = {
        "schedule_type": schedule.schedule_type,
        "recurrence": schedule.recurrence,
        "time_of_day": _response_time(schedule.time_of_day),
        "range_start": _response_time(schedule.range_start),
        "range_end": _response_time(schedule.range_end),
        "day_of_month": schedule.day_of_month,
        "month": schedule.month,
        "run_if_missed": schedule.run_if_missed,
        "misfire_grace_minutes": schedule.misfire_grace_minutes,
        "enabled": schedule.enabled,
    }
    current.update(payload.model_dump(exclude_unset=True))
    validated = ScheduleFields.model_validate(current)

    schedule = await db.schedule.update(
        where={"id": schedule_id},
        data={
            "schedule_type": validated.schedule_type.value,
            "recurrence": validated.recurrence.value,
            "time_of_day": _stored_time(validated.time_of_day),
            "range_start": _stored_time(validated.range_start),
            "range_end": _stored_time(validated.range_end),
            "day_of_month": validated.day_of_month,
            "month": validated.month,
            "run_if_missed": validated.run_if_missed,
            "misfire_grace_minutes": validated.misfire_grace_minutes,
            "enabled": validated.enabled,
            "windows_task_name": None,
            "registration_error": None,
        },
    )

    await delete_windows_task(old_task_name)
    if schedule.enabled:
        schedule = await _save_registration(db, schedule)
    return _schedule_response(schedule)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: str,
    db: Prisma = Depends(get_database),
) -> Response:
    schedule = await db.schedule.find_unique(where={"id": schedule_id})
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.schedule.delete(where={"id": schedule_id})
    await delete_windows_task(schedule.windows_task_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/run/{workflow_id}", response_model=RunResponse)
async def run_workflow(
    workflow_id: str,
    schedule_id: str | None = Query(default=None),
    db: Prisma = Depends(get_database),
) -> RunResponse:
    occurrence = None
    if schedule_id is not None:
        schedule = await db.schedule.find_unique(where={"id": schedule_id})
        if schedule is None or schedule.workflow_id != workflow_id:
            raise HTTPException(status_code=404, detail="Schedule not found for workflow")
        occurrence = due_occurrence(schedule)
        if occurrence is None:
            raise HTTPException(status_code=409, detail="Schedule is not due now")

    try:
        run = await execute_workflow(db, workflow_id, schedule_id, occurrence)
    except WorkflowExecutionError as exc:
        status_code = 404 if str(exc) == "Workflow not found" else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return _run_response(run)


@router.get("/runs", response_model=list[RunResponse])
async def list_runs(
    workflow_id: str | None = Query(default=None),
    db: Prisma = Depends(get_database),
) -> list[RunResponse]:
    where = {"workflow_id": workflow_id} if workflow_id is not None else None
    runs = await db.workflowrun.find_many(
        where=where,
        order={"created_at": "desc"},
    )
    return [_run_response(run) for run in runs]


@router.get("/runs/{run_id}/steps")
async def list_run_steps(
    run_id: str,
    db: Prisma = Depends(get_database),
) -> list[dict[str, object]]:
    if await db.workflowrun.find_unique(where={"id": run_id}) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    steps = await db.steprun.find_many(
        where={"workflow_run_id": run_id},
        order={"started_at": "asc"},
    )
    return [
        {
            "id": step.id,
            "workflow_step_id": step.workflow_step_id,
            "attempt_number": step.attempt_number,
            "status": step.status,
            "response": step.response,
            "error": step.error,
            "started_at": step.started_at,
            "finished_at": step.finished_at,
        }
        for step in steps
    ]


@router.post("/reconcile")
async def reconcile_schedules() -> dict[str, list[str]]:
    return {"triggered_run_ids": await reconcile_due_schedules()}
