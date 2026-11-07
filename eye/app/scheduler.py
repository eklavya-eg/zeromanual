import asyncio
import logging
import os
from datetime import datetime

from app.database import database
from app.execution import WorkflowExecutionError, execute_workflow
from app.schedule_engine import due_occurrence
from app.workflow_runs import WorkflowRunManager

logger = logging.getLogger(__name__)
POLL_SECONDS = max(5, int(os.getenv("SCHEDULER_POLL_SECONDS", "30")))


async def reconcile_due_schedules(
    now: datetime | None = None, *, manager: WorkflowRunManager | None = None,
) -> list[str]:
    current_time = now or datetime.now()
    schedules = await database.schedule.find_many(
        where={"enabled": True},
        include={"workflow": True},
    )

    triggered_runs: list[str] = []
    for schedule in schedules:
        if schedule.workflow is None or not schedule.workflow.enabled:
            continue
        occurrence = due_occurrence(schedule, current_time)
        if occurrence is None:
            continue
        try:
            execute = manager.submit if manager is not None else execute_workflow
            run = await execute(
                database,
                workflow_id=schedule.workflow_id,
                schedule_id=schedule.id,
                occurrence=occurrence,
            )
            triggered_runs.append(run.id)
        except WorkflowExecutionError:
            logger.exception("Scheduled workflow %s failed", schedule.workflow_id)
    return triggered_runs


async def schedule_monitor(stop_event: asyncio.Event, manager: WorkflowRunManager) -> None:
    while not stop_event.is_set():
        try:
            await reconcile_due_schedules(manager=manager)
        except Exception:
            logger.exception("Schedule reconciliation failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_SECONDS)
        except TimeoutError:
            pass
