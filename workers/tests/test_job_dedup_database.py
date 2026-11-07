import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from prisma import Prisma

from workers.jobs import JobApplicationStore, canonical_job_url
from workers.observability import ObservabilityStore


@pytest.fixture
def job_runs():
    if os.getenv('RUN_DATABASE_TESTS') != '1':
        pytest.skip('Set RUN_DATABASE_TESTS=1 with the shared database running')
    stores = [ObservabilityStore(f'test-worker-dedup-{uuid4().hex}') for _ in range(3)]
    url = f'https://EXAMPLE.com/job/{uuid4().hex}?tracking=discard#apply'
    key = canonical_job_url(url)
    run_ids = [store.start(celery_task_id=str(uuid4()), payload={'job_url': url}, job_url=url) for store in stores]
    try:
        yield stores, run_ids, url, key
    finally:
        async def cleanup():
            db = Prisma()
            await db.connect()
            try:
                await db.jobapplication.delete_many(where={'job_url': key})
                await db.workertaskrun.delete_many(where={'id': {'in': run_ids}})
                await db.worker.delete_many(where={'id': {'in': [store.worker_id for store in stores]}})
            finally:
                await db.disconnect()
        asyncio.run(cleanup())


def test_concurrent_url_claims_have_exactly_one_winner_and_duplicate_skip_is_observable(job_runs):
    stores, run_ids, url, key = job_runs
    ledger = JobApplicationStore()
    variants = [url, url.split('?')[0].replace('https://', 'http://') + '?other=1', key]
    with ThreadPoolExecutor(max_workers=3) as executor:
        claims = list(executor.map(lambda item: ledger.claim(*item), zip(variants, run_ids)))
    assert claims.count(True) == 1
    winner = claims.index(True)
    for i, store in enumerate(stores):
        if i == winner:
            store.finish(succeeded=True, result={'status': 'succeeded'})
        else:
            store.finish(succeeded=False, skip_reason='duplicate', skip_details='URL already claimed', job_url=url,
                         result={'status': 'skipped', 'skip_reason': 'duplicate'})

    async def verify():
        db = Prisma()
        await db.connect()
        try:
            identity = await db.jobapplication.find_unique(where={'job_url': key})
            assert identity.first_run_id == run_ids[winner]
            assert identity.status == 'succeeded'
            for i, run_id in enumerate(run_ids):
                run = await db.workertaskrun.find_unique(where={'id': run_id})
                assert run.job_url == key
                assert run.payload['job_url'] == key
                logs = await db.workerlog.find_many(where={'task_run_id': run_id})
                assert logs
                if i != winner:
                    assert run.status == 'skipped'
                    assert not run.success and not run.failed
                    skip = await db.workerskip.find_unique(where={'task_run_id': run_id})
                    assert skip.reason == 'duplicate' and skip.job_url == key
        finally:
            await db.disconnect()
    asyncio.run(verify())


def test_redflag_keeps_identity_and_records_skip_without_failure(job_runs):
    stores, run_ids, url, key = job_runs
    ledger = JobApplicationStore()
    assert ledger.claim(url, run_ids[0])
    stores[0].finish(succeeded=False, skip_reason='redflag', skip_details='Data analyst role excluded', job_url=url,
                     result={'status': 'skipped', 'skip_reason': 'redflag'})
    assert not ledger.claim(key, run_ids[1])

    async def verify():
        db = Prisma()
        await db.connect()
        try:
            identity = await db.jobapplication.find_unique(where={'job_url': key})
            skip = await db.workerskip.find_unique(where={'task_run_id': run_ids[0]})
            run = await db.workertaskrun.find_unique(where={'id': run_ids[0]})
            assert identity.status == 'redflag'
            assert identity.reason == skip.details == 'Data analyst role excluded'
            assert run.status == 'skipped' and not run.failed and not run.success
            assert skip.reason == 'redflag'
        finally:
            await db.disconnect()
    asyncio.run(verify())


def test_celery_entrypoint_records_duplicate_skip_before_constructing_worker(job_runs, monkeypatch):
    from types import SimpleNamespace
    from workers import tasks

    stores, run_ids, url, key = job_runs
    assert JobApplicationStore().claim(url, run_ids[0])
    monkeypatch.setattr(tasks, 'load_settings', lambda: SimpleNamespace(worker_name=stores[1].worker_name))
    monkeypatch.setattr(tasks, 'JobApplicationWorker', lambda *args: pytest.fail('Duplicate started browser/LLM work'))
    task_id = str(uuid4())
    result = tasks.apply_to_job.apply(args=[{
        'job_url': url.split('?')[0] + '?different=tracking',
        'job_title': 'Backend Engineer', 'company_name': 'Test Company',
    }], task_id=task_id, throw=True).result
    # Include this delivery in fixture cleanup.
    run_ids.append(result['task_run_id'])
    assert result['status'] == 'skipped' and result['skip_reason'] == 'duplicate'

    async def verify():
        db = Prisma()
        await db.connect()
        try:
            run = await db.workertaskrun.find_unique(where={'celery_task_id': task_id})
            skip = await db.workerskip.find_unique(where={'task_run_id': run.id})
            assert run.status == 'skipped' and not run.failed
            assert run.job_url == run.payload['job_url'] == skip.job_url == key
            assert skip.reason == 'duplicate'
        finally:
            await db.disconnect()
    asyncio.run(verify())


def test_failed_attempt_still_blocks_automatic_reapplication(job_runs):
    stores, run_ids, url, key = job_runs
    ledger = JobApplicationStore()
    assert ledger.claim(url, run_ids[0])
    stores[0].finish(succeeded=False, error='Ambiguous application response', step_failed='apply_to_job')
    assert not ledger.claim(url, run_ids[1])

    async def verify():
        db = Prisma()
        await db.connect()
        try:
            identity = await db.jobapplication.find_unique(where={'job_url': key})
            assert identity.status == 'failed'
            assert identity.reason == 'Ambiguous application response'
        finally:
            await db.disconnect()
    asyncio.run(verify())
