import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from celery import Celery
from celery.signals import worker_ready
from prisma import Prisma

from workers import celery_app as module
from workers.registration import register_worker


def test_celery_ready_registers_worker_without_a_task(monkeypatch):
    registrations = []
    monkeypatch.setattr(module, 'register_worker', lambda name: registrations.append(name))
    monkeypatch.setattr(module, 'load_settings', lambda: SimpleNamespace(worker_name='ready-worker'))
    class Sender:
        app = module.celery_app

    replies = worker_ready.send(sender=Sender())
    assert registrations == ['ready-worker']
    assert not any(isinstance(response, Exception) for _, response in replies)
    module.register_worker_on_ready(sender=SimpleNamespace(app=Celery('unrelated-app')))
    assert registrations == ['ready-worker']


def test_registration_is_idempotent_and_does_not_create_task_runs():
    if os.getenv('RUN_DATABASE_TESTS') != '1':
        pytest.skip('Set RUN_DATABASE_TESTS=1 with the shared database running')
    name = f'test-registration-{uuid4().hex}'
    worker_id = register_worker(name)
    try:
        assert register_worker(name) == worker_id

        async def verify():
            db = Prisma()
            await db.connect()
            try:
                worker = await db.worker.find_unique(where={'id': worker_id})
                assert worker.name == name
                assert worker.enabled is True
                assert await db.worker.count(where={'name': name}) == 1
                assert await db.workertaskrun.count(where={'worker_id': worker_id}) == 0
            finally:
                await db.disconnect()
        asyncio.run(verify())
    finally:
        async def cleanup():
            db = Prisma()
            await db.connect()
            try:
                await db.worker.delete(where={'id': worker_id})
            finally:
                await db.disconnect()
        asyncio.run(cleanup())
