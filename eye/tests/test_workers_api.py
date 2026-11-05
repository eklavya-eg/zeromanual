import asyncio
from uuid import uuid4

from prisma import Json, Prisma


def test_worker_observability_api(client) -> None:
    worker_name = f"api-worker-{uuid4().hex}"

    async def seed() -> tuple[str, str]:
        db = Prisma()
        await db.connect()
        try:
            worker = await db.worker.create(data={"name": worker_name})
            run = await db.workertaskrun.create(
                data={
                    "worker_id": worker.id,
                    "celery_task_id": str(uuid4()),
                    "job_url": "https://example.com/job",
                    "payload": Json({"job_url": "https://example.com/job"}),
                    "status": "failed",
                    "failed": True,
                    "step_failed": "apply_to_job",
                }
            )
            await db.workerlog.create(
                data={
                    "worker_id": worker.id,
                    "task_run_id": run.id,
                    "level": "error",
                    "step": "apply_to_job",
                    "message": "Browser unavailable",
                }
            )
            return worker.id, run.id
        finally:
            await db.disconnect()

    worker_id, run_id = asyncio.run(seed())
    try:
        workers = client.get("/api/workers")
        runs = client.get("/api/workers/runs", params={"worker_id": worker_id})
        run = client.get(f"/api/workers/runs/{run_id}")
        logs = client.get(f"/api/workers/runs/{run_id}/logs")
        dashboard = client.get(f"/api/workers/{worker_id}/dashboard")

        assert dashboard.status_code == 200
        data = dashboard.json()
        assert data["worker"]["id"] == worker_id
        assert data["metrics"] == {
            "total_runs": 1,
            "running": 0,
            "succeeded": 0,
            "failed": 1,
            "success_rate": 0.0,
        }
        assert data["total"] == 1
        assert data["runs"][0]["id"] == run_id
        assert workers.status_code == 200
        assert any(item["id"] == worker_id for item in workers.json())
        assert runs.status_code == 200
        assert runs.json()[0]["step_failed"] == "apply_to_job"
        assert run.status_code == 200
        assert run.json()["failed"] is True
        assert logs.status_code == 200
        assert logs.json()[0]["message"] == "Browser unavailable"
    finally:
        async def cleanup() -> None:
            db = Prisma()
            await db.connect()
            try:
                await db.workertaskrun.delete(where={"id": run_id})
                await db.worker.delete(where={"id": worker_id})
            finally:
                await db.disconnect()

        asyncio.run(cleanup())
