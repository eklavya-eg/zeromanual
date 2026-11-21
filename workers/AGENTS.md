# Workers

[Repository map](../AGENTS.md) | [Setup and processing details](README.md)

## Purpose and worker types

This Python/Celery project owns long-running background workers. Worker types
belong in the [handlers package](workers/handlers/), separate from Celery task
entrypoints and shared infrastructure. Currently the concrete implementation is
[JobApplicationWorker](workers/handlers/job_application.py); do not assume
additional worker types already exist.

The application worker claims a job identity, loads the candidate profile and
resume, fetches the job description through Browser Agent, checks eligibility
and tailors the resume with an LLM, renders a PDF, and applies using the same
browser session. Duplicate or red-flag jobs are skipped. The browser is closed
when processing finishes, while resume artifacts remain available.

## Code map

- [workers/celery_app.py](workers/celery_app.py): broker, queue routing, and
  startup registration; [workers/tasks.py](workers/tasks.py): `workers.apply_to_job`.
- [workers/handlers/job_application.py](workers/handlers/job_application.py):
  independently testable application processing steps.
- [workers/jobs.py](workers/jobs.py): canonical job identity and database claims.
- [workers/observability.py](workers/observability.py) and
  [workers/registration.py](workers/registration.py): run state, buffered logs,
  and worker registration in Eye's database.
- [workers/settings.py](workers/settings.py), [workers/schemas.py](workers/schemas.py),
  [workers/retry.py](workers/retry.py), and [workers/llm.py](workers/llm.py):
  configuration, payload/result contracts, retry, and LLM helpers.
- [static](static/): local candidate inputs; [output](output/): generated
  per-execution resume artifacts; [tests](tests/): worker behavior tests.

## Commands

Run from this directory with a private environment configured:

```powershell
uv sync
uv run prisma generate --schema ..\eye\prisma\schema.prisma
uv run pytest -q
```

Start a consumer only when processing queued applications is intended:

```powershell
uv run celery -A workers.celery_app:celery_app worker --loglevel=INFO --pool=solo -Q job-applications
```

The queue argument must match `WORKER_QUEUE` if changed. Runtime dependencies
include PostgreSQL, Redis, Browser Agent, LLM credentials, and a browser usable
by the [resume renderer](../resume-template-engine/AGENTS.md).

## Change boundaries

- Add new worker types under handlers and explicitly wire their task names,
  payloads, routing, registration, and observability. Reuse existing helpers.
- [Eye's schema](../eye/prisma/schema.prisma) is the database source of truth.
  Both services must share `DATABASE_URL` and regenerate clients after changes.
- Preserve atomic domain/path job claims before browser or LLM work. A failed
  or skipped claim is not automatically eligible for replay.
- Keep skipped runs distinct from success and failure. Logs are buffered during
  work and flushed with final state; registration is not a live heartbeat.
- Never invent candidate facts. Keep resume artifacts isolated by run and resume
  UUID, and authorize only the current PDF through `available_file_paths`.
- Preserve the shared browser session between retrieval and application, plus
  final cleanup. Avoid retries that can submit the same application twice.
