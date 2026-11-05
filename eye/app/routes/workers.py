from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from prisma import Prisma
from prisma.types import WorkerTaskRunWhereInput

from app.database import get_database
from app.schemas import (
    WorkerDashboardResponse,
    WorkerLogResponse,
    WorkerMetricsResponse,
    WorkerResponse,
    WorkerTaskRunResponse,
)

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("", response_model=list[WorkerResponse])
async def list_workers(db: Prisma = Depends(get_database)) -> list[WorkerResponse]:
    workers = await db.worker.find_many(order={"created_at": "asc"})
    return [WorkerResponse.model_validate(worker) for worker in workers]


@router.get("/runs", response_model=list[WorkerTaskRunResponse])
async def list_worker_runs(
    worker_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Prisma = Depends(get_database),
) -> list[WorkerTaskRunResponse]:
    where = {}
    if worker_id is not None:
        where["worker_id"] = worker_id
    if status is not None:
        where["status"] = status
    runs = await db.workertaskrun.find_many(
        where=where or None,
        order={"started_at": "desc"},
    )
    return [WorkerTaskRunResponse.model_validate(run) for run in runs]


@router.get("/runs/{task_run_id}", response_model=WorkerTaskRunResponse)
async def get_worker_run(
    task_run_id: str,
    db: Prisma = Depends(get_database),
) -> WorkerTaskRunResponse:
    run = await db.workertaskrun.find_unique(where={"id": task_run_id})
    if run is None:
        raise HTTPException(status_code=404, detail="Worker task run not found")
    return WorkerTaskRunResponse.model_validate(run)


@router.get("/runs/{task_run_id}/logs", response_model=list[WorkerLogResponse])
async def list_worker_logs(
    task_run_id: str,
    db: Prisma = Depends(get_database),
) -> list[WorkerLogResponse]:
    if await db.workertaskrun.find_unique(where={"id": task_run_id}) is None:
        raise HTTPException(status_code=404, detail="Worker task run not found")
    logs = await db.workerlog.find_many(
        where={"task_run_id": task_run_id},
        order={"created_at": "asc"},
    )
    return [WorkerLogResponse.model_validate(log) for log in logs]


@router.get("/{worker_id}/dashboard", response_model=WorkerDashboardResponse)
async def get_worker_dashboard(
    worker_id: UUID,
    status: Literal["running", "succeeded", "failed"] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Prisma = Depends(get_database),
) -> WorkerDashboardResponse:
    worker_key = str(worker_id)
    worker = await db.worker.find_unique(where={"id": worker_key})
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker not found")

    groups = await db.workertaskrun.group_by(
        by=["status"],
        where={"worker_id": worker_key},
        count={"id": True},
    )
    counts = {group["status"]: group["_count"]["id"] for group in groups}
    total_runs = sum(counts.values())
    succeeded = counts.get("succeeded", 0)
    failed = counts.get("failed", 0)
    completed = succeeded + failed
    where: WorkerTaskRunWhereInput = {"worker_id": worker_key}
    if status is not None:
        where["status"] = status
    runs = await db.workertaskrun.find_many(
        where=where,
        order=[{"started_at": "desc"}, {"id": "desc"}],
        skip=(page - 1) * page_size,
        take=page_size,
    )
    return WorkerDashboardResponse(
        worker=WorkerResponse.model_validate(worker),
        metrics=WorkerMetricsResponse(
            total_runs=total_runs,
            running=counts.get("running", 0),
            succeeded=succeeded,
            failed=failed,
            success_rate=round(succeeded / completed * 100, 1) if completed else None,
        ),
        runs=[WorkerTaskRunResponse.model_validate(run) for run in runs],
        total=counts.get(status, 0) if status is not None else total_runs,
        page=page,
        page_size=page_size,
    )
