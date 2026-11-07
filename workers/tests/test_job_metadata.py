import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from prisma import Prisma

from workers.jobs import JobApplicationStore, canonical_job_url, job_metadata
from workers.observability import ObservabilityStore
from workers.settings import JobApplicationPayload


def job_payload(**overrides):
    return {
        "job_url": "https://www.naukri.com/job-listings-example-123",
        "company_name": "Example Company",
        "job_title": "Backend Engineer",
        "package": "INR 12–18 LPA",
        "platform": "Naukri",
        **overrides,
    }


@pytest.mark.parametrize("missing", [None, "", "  ", "n/a", "Not disclosed"])
def test_optional_job_metadata_defaults_to_na(missing):
    payload = JobApplicationPayload.model_validate(job_payload(package=missing, platform=missing))
    assert payload.package == payload.platform == "NA"
    assert job_metadata(payload.model_dump())["package"] == "NA"


def test_worker_payload_preserves_all_metadata_and_supports_old_messages():
    payload = JobApplicationPayload.model_validate(job_payload(package=" INR 12–18 LPA ", platform=" Naukri "))
    assert payload.package == "INR 12–18 LPA"
    assert payload.platform == "Naukri"
    old = JobApplicationPayload.model_validate({
        "job_url": "https://example.com/job", "job_title": "Engineer", "company_name": "Company",
    })
    assert old.package == old.platform == "NA"
    assert job_metadata({}) == dict.fromkeys(["company_name", "job_title", "package", "platform"], "NA")


def test_observability_and_ledger_write_metadata_columns(monkeypatch):
    captured = {}

    async def connect():
        pass

    async def upsert(**kwargs):
        return SimpleNamespace(id="worker-id")

    async def create_run(*, data):
        captured["run"] = data
        return SimpleNamespace(id="run-id")

    async def create_job(*, data):
        captured["job"] = data

    fake = SimpleNamespace(
        connect=connect, disconnect=connect,
        worker=SimpleNamespace(upsert=upsert),
        workertaskrun=SimpleNamespace(create=create_run),
        jobapplication=SimpleNamespace(create=create_job),
    )
    monkeypatch.setattr("workers.observability.Prisma", lambda: fake)
    monkeypatch.setattr("workers.jobs.Prisma", lambda: fake)
    data = job_payload()
    run_id = ObservabilityStore("test-worker").start(celery_task_id="task", payload=data, job_url=data["job_url"])
    assert JobApplicationStore().claim(data["job_url"], run_id, payload=data)
    expected = {**job_metadata(data), "job_url": canonical_job_url(data["job_url"])}
    for record in captured.values():
        assert {field: record[field] for field in expected} == expected


def test_complete_job_metadata_is_persisted_in_database_for_duplicate_attempts():
    if os.getenv("RUN_DATABASE_TESTS") != "1":
        pytest.skip("Set RUN_DATABASE_TESTS=1 with the shared database running")
    stores = [ObservabilityStore(f"test-job-metadata-{uuid4().hex}") for _ in range(2)]
    url = f"https://www.naukri.com/job-listings-test-{uuid4().hex}"
    payloads = [job_payload(job_url=url), job_payload(job_url=url, package=None)]
    runs = []
    try:
        for store, data in zip(stores, payloads):
            runs.append(store.start(celery_task_id=str(uuid4()), payload=data, job_url=url))
        ledger = JobApplicationStore()
        assert ledger.claim(url, runs[0], payload=payloads[0])
        assert not ledger.claim(url, runs[1], payload=payloads[1])
        stores[0].finish(succeeded=True, result={"status": "succeeded"})
        stores[1].finish(succeeded=False, skip_reason="duplicate", skip_details="Already claimed", job_url=url)

        async def verify():
            db = Prisma()
            await db.connect()
            try:
                job = await db.jobapplication.find_unique(where={"job_url": canonical_job_url(url)})
                for run_id, data in zip(runs, payloads):
                    run = await db.workertaskrun.find_unique(where={"id": run_id})
                    for field, expected in job_metadata(data).items():
                        assert getattr(run, field) == expected
                        assert run.payload[field] == expected
                    assert run.job_url == canonical_job_url(url)
                assert job.package == "INR 12–18 LPA"
                assert job.company_name == "Example Company"
                assert job.job_title == "Backend Engineer"
                assert job.platform == "Naukri"
            finally:
                await db.disconnect()

        asyncio.run(verify())
    finally:
        async def cleanup():
            db = Prisma()
            await db.connect()
            try:
                await db.jobapplication.delete_many(where={"job_url": canonical_job_url(url)})
                await db.workertaskrun.delete_many(where={"id": {"in": runs}})
                await db.worker.delete_many(where={"name": {"in": [store.worker_name for store in stores]}})
            finally:
                await db.disconnect()

        asyncio.run(cleanup())


def test_metadata_migration_backfills_existing_payloads_without_inventing_pay():
    if os.getenv("RUN_DATABASE_TESTS") != "1":
        pytest.skip("Set RUN_DATABASE_TESTS=1 with the shared database running")

    async def scenario():
        db = Prisma()
        await db.connect()
        schema = f"test_job_metadata_{uuid4().hex}"
        runs = f'"{schema}"."worker_task_runs"'
        jobs = f'"{schema}"."job_applications"'
        migration = Path(__file__).resolve().parents[2] / "eye" / "prisma" / "migrations" / "20261107174500_job_metadata" / "migration.sql"
        script = migration.read_text(encoding="utf-8").replace('"worker_task_runs"', runs).replace('"job_applications"', jobs)
        try:
            await db.execute_raw(f'CREATE SCHEMA "{schema}"')
            await db.execute_raw(f'CREATE TABLE {runs} (id UUID PRIMARY KEY, job_url TEXT NOT NULL, payload JSONB NOT NULL)')
            await db.execute_raw(f'CREATE TABLE {jobs} (job_url TEXT PRIMARY KEY, first_run_id UUID)')
            records = [
                (str(uuid4()), "www.naukri.com/jobs/1", job_payload()),
                (str(uuid4()), "www.naukri.com/jobs/2", {"company_name": "Old Company", "job_title": "Engineer"}),
                (str(uuid4()), "example.com/jobs/3", {"company_name": None, "job_title": "", "package": None}),
                (str(uuid4()), "example.com/jobs/4", {"company_name": "Company", "job_title": "Role", "package": " n/a ", "platform": " LinkedIn "}),
            ]
            for run_id, url, data in records:
                await db.execute_raw(f'INSERT INTO {runs} VALUES ($1::uuid, $2, $3::jsonb)', run_id, url, json.dumps(data))
                await db.execute_raw(f'INSERT INTO {jobs} VALUES ($1, $2::uuid)', url, run_id)
            async with db.tx() as tx:
                for statement in script.split(";"):
                    if statement.strip() and statement.strip() not in {"BEGIN", "COMMIT"}:
                        await tx.execute_raw(statement)
            rows = await db.query_raw(f'SELECT * FROM {runs} ORDER BY job_url')
            by_url = {row["job_url"]: row for row in rows}
            assert by_url["www.naukri.com/jobs/1"]["package"] == "INR 12–18 LPA"
            assert by_url["www.naukri.com/jobs/2"]["company_name"] == "Old Company"
            assert by_url["www.naukri.com/jobs/2"]["job_title"] == "Engineer"
            assert by_url["www.naukri.com/jobs/2"]["package"] == "NA"
            assert by_url["www.naukri.com/jobs/2"]["platform"] == "Naukri"
            assert all(by_url["example.com/jobs/3"][field] == "NA" for field in ["company_name", "job_title", "package", "platform"])
            assert by_url["example.com/jobs/4"]["package"] == "NA"
            assert by_url["example.com/jobs/4"]["platform"] == "LinkedIn"
            ledger = await db.query_raw(f'SELECT * FROM {jobs}')
            for row in ledger:
                for field in ["company_name", "job_title", "package", "platform"]:
                    assert row[field] == by_url[row["job_url"]][field]
        finally:
            await db.execute_raw(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await db.disconnect()

    asyncio.run(scenario())
