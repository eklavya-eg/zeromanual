import asyncio
from uuid import uuid4

from prisma import Json, Prisma


def test_skip_endpoint_and_skipped_dashboard_filter(client):
    async def seed():
        db = Prisma()
        await db.connect()
        try:
            worker = await db.worker.create(data={'name': f'skip-api-test-{uuid4().hex}'})
            run = await db.workertaskrun.create(data={
                'worker_id': worker.id, 'celery_task_id': str(uuid4()),
                'job_url': 'example.com/job', 'payload': Json({'job_url': 'example.com/job'}),
                'status': 'skipped',
            })
            await db.workerskip.create(data={
                'task_run_id': run.id, 'job_url': 'example.com/job',
                'reason': 'redflag', 'details': 'Data analyst roles are excluded',
            })
            return worker.id, run.id
        finally:
            await db.disconnect()

    worker_id, run_id = asyncio.run(seed())
    try:
        skip = client.get(f'/api/workers/runs/{run_id}/skip')
        assert skip.status_code == 200
        assert skip.json()['reason'] == 'redflag'
        assert skip.json()['job_url'] == 'example.com/job'
        dashboard = client.get(f'/api/workers/{worker_id}/dashboard', params={'status': 'skipped'})
        assert dashboard.status_code == 200
        data = dashboard.json()
        assert data['metrics']['skipped'] == data['total'] == 1
        assert data['metrics']['success_rate'] is None
        assert data['runs'][0]['status'] == 'skipped'
        assert not data['runs'][0]['success'] and not data['runs'][0]['failed']
        assert client.get(f'/api/workers/runs/{uuid4()}/skip').status_code == 404
    finally:
        async def cleanup():
            db = Prisma()
            await db.connect()
            try:
                await db.workertaskrun.delete(where={'id': run_id})
                await db.worker.delete(where={'id': worker_id})
            finally:
                await db.disconnect()
        asyncio.run(cleanup())
