import asyncio
from uuid import uuid4

from prisma import Json, Prisma


def test_dashboard_metrics_filters_pagination_and_worker_isolation(client) -> None:
    async def seed() -> tuple[str, str]:
        db = Prisma()
        await db.connect()
        try:
            worker = await db.worker.create(data={"name": f"dashboard-{uuid4().hex}"})
            other = await db.worker.create(data={"name": f"dashboard-{uuid4().hex}"})
            await db.workertaskrun.create_many(
                data=[
                    {
                        "worker_id": owner,
                        "celery_task_id": str(uuid4()),
                        "job_url": "https://example.com/job",
                        "payload": Json({"job_url": "https://example.com/job"}),
                        "status": status,
                        "success": status == "succeeded",
                        "failed": status == "failed",
                    }
                    for owner, status in [
                        (worker.id, "succeeded"),
                        (worker.id, "failed"),
                        (worker.id, "running"),
                        (other.id, "succeeded"),
                    ]
                ]
            )
            return worker.id, other.id
        finally:
            await db.disconnect()

    worker_id, other_id = asyncio.run(seed())
    try:
        base = f"/api/workers/{worker_id}/dashboard"
        first = client.get(base, params={"page_size": 2}).json()
        second = client.get(base, params={"page_size": 2, "page": 2}).json()
        filtered = client.get(base, params={"status": "failed"}).json()
        assert first["metrics"] == {
            "total_runs": 3,
            "running": 1,
            "succeeded": 1,
            "failed": 1,
            "success_rate": 50.0,
        }
        assert first["total"] == 3
        assert len(first["runs"]) == 2
        assert len(second["runs"]) == 1
        assert {run["id"] for run in first["runs"]}.isdisjoint(
            run["id"] for run in second["runs"]
        )
        assert all(run["worker_id"] == worker_id for run in first["runs"] + second["runs"])
        assert filtered["total"] == 1
        assert filtered["runs"][0]["status"] == "failed"
        assert filtered["metrics"] == first["metrics"]
        assert client.get(base, params={"page": 10}).json()["runs"] == []
        for params in [{"page": 0}, {"page_size": 101}, {"status": "unknown"}]:
            assert client.get(base, params=params).status_code == 422
        assert client.get(f"/api/workers/{uuid4()}/dashboard").status_code == 404
        assert client.get("/api/workers/not-a-uuid/dashboard").status_code == 422
    finally:
        async def cleanup() -> None:
            db = Prisma()
            await db.connect()
            try:
                await db.workertaskrun.delete_many(where={"worker_id": {"in": [worker_id, other_id]}})
                await db.worker.delete_many(where={"id": {"in": [worker_id, other_id]}})
            finally:
                await db.disconnect()

        asyncio.run(cleanup())


def test_dashboard_for_worker_without_runs(client) -> None:
    async def create_worker() -> str:
        db = Prisma()
        await db.connect()
        try:
            worker = await db.worker.create(data={"name": f"empty-dashboard-{uuid4().hex}"})
            return worker.id
        finally:
            await db.disconnect()

    worker_id = asyncio.run(create_worker())
    try:
        response = client.get(f"/api/workers/{worker_id}/dashboard")
        assert response.status_code == 200
        assert response.json()["runs"] == []
        assert response.json()["total"] == 0
        assert response.json()["metrics"]["total_runs"] == 0
        assert response.json()["metrics"]["success_rate"] is None
    finally:
        async def cleanup() -> None:
            db = Prisma()
            await db.connect()
            try:
                await db.worker.delete(where={"id": worker_id})
            finally:
                await db.disconnect()

        asyncio.run(cleanup())
