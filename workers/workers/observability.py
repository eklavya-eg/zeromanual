import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from prisma import Json, Prisma

from workers.jobs import canonical_job_url, job_metadata
from workers.registration import upsert_worker


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class BufferedLog:
    level: str
    step: str
    message: str
    details: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=utc_now)


class ObservabilityStore:
    def __init__(self, worker_name: str) -> None:
        self.worker_name = worker_name
        self.worker_id: str | None = None
        self.task_run_id: str | None = None
        self.logs: list[BufferedLog] = []

    def start(self, *, celery_task_id: str, payload: dict[str, Any], job_url: str) -> str:
        job_url = canonical_job_url(job_url)
        metadata = job_metadata(payload)
        payload = {**payload, **metadata, "job_url": job_url}

        async def operation() -> tuple[str, str]:
            db = Prisma()
            await db.connect()
            try:
                worker = await upsert_worker(db, self.worker_name)
                run = await db.workertaskrun.create(
                    data={
                        "worker_id": worker.id,
                        "celery_task_id": celery_task_id,
                        "job_url": job_url,
                        **metadata,
                        "payload": Json(payload),
                        "status": "running",
                        "started": True,
                    }
                )
                return worker.id, run.id
            finally:
                await db.disconnect()

        self.worker_id, self.task_run_id = asyncio.run(operation())
        self.add("info", "start", "Worker task started")
        return self.task_run_id

    def add(
        self,
        level: str,
        step: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.logs.append(BufferedLog(level, step, message, details))

    def retry(self, step: str, attempt: int, delay: float, exc: Exception) -> None:
        self.add(
            "warning",
            step,
            f"Network call failed; retrying in {delay:g}s",
            {"attempt": attempt, "error": str(exc)},
        )

    def finish(
        self,
        *,
        succeeded: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        step_failed: str | None = None,
        skip_reason: str | None = None,
        skip_details: str | None = None,
        job_url: str | None = None,
    ) -> None:
        if self.worker_id is None or self.task_run_id is None:
            raise RuntimeError("Observability run was not started")

        skipped = skip_reason is not None
        if skipped and (succeeded or skip_reason not in {"duplicate", "redflag"} or not skip_details or not job_url):
            raise ValueError("A skipped run requires a valid reason, details, URL, and succeeded=False")
        status = "skipped" if skipped else "succeeded" if succeeded else "failed"
        self.add(
            "info" if succeeded or skipped else "error",
            "complete",
            f"Worker task {status}",
            {"step_failed": step_failed, "skip_reason": skip_reason},
        )

        async def operation() -> None:
            db = Prisma()
            await db.connect()
            try:
                async with db.tx() as tx:
                    if self.logs:
                        log_rows = []
                        for log in self.logs:
                            row = {
                                "worker_id": self.worker_id,
                                "task_run_id": self.task_run_id,
                                "level": log.level,
                                "step": log.step,
                                "message": log.message,
                                "created_at": log.created_at,
                            }
                            if log.details is not None:
                                row["details"] = Json(log.details)
                            log_rows.append(row)
                        await tx.workerlog.create_many(data=log_rows)
                    run_update = {
                        "status": status,
                        "success": succeeded,
                        "failed": not succeeded and not skipped,
                        "step_failed": step_failed,
                        "error": error,
                        "finished_at": utc_now(),
                    }
                    if result is not None:
                        run_update["result"] = Json(result)
                    await tx.workertaskrun.update(where={"id": self.task_run_id}, data=run_update)
                    if skipped:
                        await tx.workerskip.create(data={
                            "task_run_id": self.task_run_id,
                            "job_url": canonical_job_url(job_url),
                            "reason": skip_reason,
                            "details": skip_details,
                        })
                    # Only the original claiming run may change the job's terminal outcome.
                    await tx.jobapplication.update_many(
                        where={"first_run_id": self.task_run_id},
                        data={"status": "redflag" if skip_reason == "redflag" else status,
                              "reason": skip_details if skipped else error},
                    )
            finally:
                await db.disconnect()

        asyncio.run(operation())
        self.logs.clear()
