import asyncio
import logging

from prisma import Prisma
from prisma.models import WorkflowRun
from redis.exceptions import RedisError

from app.execution import WorkflowExecutionError, execute_claimed_workflow, prepare_workflow_run
from app.notifications import NotificationStore
from app.schedule_engine import DueOccurrence

logger = logging.getLogger(__name__)


class WorkflowRunManager:
    def __init__(self, notifications: NotificationStore) -> None:
        self.notifications = notifications
        self.tasks: set[asyncio.Task[None]] = set()
        self.lock = asyncio.Lock()
        self.closed = False

    async def submit(
        self,
        db: Prisma,
        workflow_id: str,
        schedule_id: str | None = None,
        occurrence: DueOccurrence | None = None,
    ) -> WorkflowRun:
        async with self.lock:
            if self.closed:
                raise WorkflowExecutionError("Workflow runner is shutting down")
            workflow, run, claimed = await prepare_workflow_run(db, workflow_id, schedule_id, occurrence)
            if claimed:
                task = asyncio.create_task(self._execute(db, run, workflow.name))
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)
            return run

    async def _execute(self, db: Prisma, run: WorkflowRun, workflow_name: str) -> None:
        try:
            try:
                await execute_claimed_workflow(db, run)
            except (WorkflowExecutionError, asyncio.CancelledError):
                pass
            completed = await db.workflowrun.find_unique(where={"id": run.id})
            if completed is None or completed.status not in {"succeeded", "failed"}:
                return
            for attempt in range(3):
                try:
                    await self.notifications.publish_workflow_run(completed, workflow_name)
                    break
                except RedisError:
                    if attempt == 2:
                        logger.exception("Could not publish workflow completion for %s; run remains in PostgreSQL", run.id)
                    else:
                        await asyncio.sleep(2**attempt)
        except Exception:
            logger.exception("Detached workflow execution failed for %s", run.id)

    async def close(self) -> None:
        async with self.lock:
            self.closed = True
            tasks = list(self.tasks)
        # Let newly accepted tasks enter their cancellation/finalization handlers first.
        await asyncio.sleep(0)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
