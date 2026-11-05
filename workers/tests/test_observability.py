import asyncio
import os
from uuid import uuid4

import pytest
from prisma import Prisma

from workers.observability import ObservabilityStore


def test_observability_flushes_buffer_on_success() -> None:
    if os.getenv("RUN_DATABASE_TESTS") != "1":
        pytest.skip("Set RUN_DATABASE_TESTS=1 with the Eye database running")

    celery_task_id = str(uuid4())
    store = ObservabilityStore(f"test-worker-{uuid4().hex}")
    run_id = store.start(
        celery_task_id=celery_task_id,
        payload={"job_url": "https://example.com/job"},
        job_url="https://example.com/job",
    )
    store.add("info", "tailor_resume", "Structured response received")
    store.finish(succeeded=True, result={"status": "ok"})

    async def verify_and_cleanup() -> None:
        db = Prisma()
        await db.connect()
        try:
            run = await db.workertaskrun.find_unique(where={"id": run_id})
            logs = await db.workerlog.find_many(where={"task_run_id": run_id})
            assert run is not None
            assert run.started is True
            assert run.success is True
            assert run.failed is False
            assert run.status == "succeeded"
            assert {log.step for log in logs} >= {"start", "tailor_resume", "complete"}
            await db.workertaskrun.delete(where={"id": run_id})
            await db.worker.delete(where={"id": store.worker_id})
        finally:
            await db.disconnect()

    asyncio.run(verify_and_cleanup())


def test_observability_flushes_buffer_on_failure() -> None:
    if os.getenv("RUN_DATABASE_TESTS") != "1":
        pytest.skip("Set RUN_DATABASE_TESTS=1 with the Eye database running")

    store = ObservabilityStore(f"test-worker-{uuid4().hex}")
    run_id = store.start(
        celery_task_id=str(uuid4()),
        payload={"job_url": "https://example.com/job"},
        job_url="https://example.com/job",
    )
    store.add("error", "apply_to_job", "Browser call exhausted retries")
    store.finish(
        succeeded=False,
        error="browser unavailable",
        step_failed="apply_to_job",
    )

    async def verify_and_cleanup() -> None:
        db = Prisma()
        await db.connect()
        try:
            run = await db.workertaskrun.find_unique(where={"id": run_id})
            logs = await db.workerlog.find_many(where={"task_run_id": run_id})
            assert run is not None
            assert run.success is False
            assert run.failed is True
            assert run.status == "failed"
            assert run.step_failed == "apply_to_job"
            assert any(log.level == "error" for log in logs)
            await db.workertaskrun.delete(where={"id": run_id})
            await db.worker.delete(where={"id": store.worker_id})
        finally:
            await db.disconnect()

    asyncio.run(verify_and_cleanup())
