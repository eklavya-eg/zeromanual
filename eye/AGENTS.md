# Eye

[Repository map](../AGENTS.md) | [Setup and API details](README.md)

## Purpose

Eye is the FastAPI backend for the operations dashboard. It manages sub-agent
registration and manual trial invocations, ordered workflow stacks, scheduling,
run history, notifications, and worker dashboards. It orchestrates browser
services and local commands; browser automation itself belongs to
[Browser Agent](../browseragent/AGENTS.md).

PostgreSQL holds durable workflow and worker records. Redis holds ephemeral
manual invocation jobs and notification history. Schedules use Windows Task
Scheduler callbacks plus an in-process reconciliation monitor.

## Code map

- [main.py](main.py): local server entrypoint, port `8000`.
- [app/app.py](app/app.py): application lifecycle, CORS, and API router wiring.
- [app/routes](app/routes/): scheduled workflow/sub-agent, notification, and
  worker endpoints.
- [app/schemas.py](app/schemas.py) and [app/models.py](app/models.py): API models.
- [app/execution.py](app/execution.py), [app/workflow_runs.py](app/workflow_runs.py),
  and [app/commands.py](app/commands.py): step execution, managed background runs,
  and command process/output handling.
- [app/schedule_engine.py](app/schedule_engine.py),
  [app/scheduler.py](app/scheduler.py), and
  [app/windows_scheduler.py](app/windows_scheduler.py): occurrence calculation,
  reconciliation, and OS task registration.
- [app/notifications.py](app/notifications.py): Redis correlation and notification
  delivery; [app/database.py](app/database.py): Prisma connection lifecycle.
- [prisma/schema.prisma](prisma/schema.prisma) and
  [prisma/migrations](prisma/migrations/): shared database schema and migrations.
- [tests](tests/): API, execution, scheduling, notification, and worker-view tests.

## Commands

Run from this directory. Configure the private environment, provision PostgreSQL
and Redis, and apply the documented migrations before starting the service:

```powershell
uv sync
uv run prisma generate
uv run pytest -q
uv run python main.py
```

OpenAPI is at `http://127.0.0.1:8000/docs`. Database/Redis integration tests are
opt-in; see the README before enabling them against a configured instance.

## Change boundaries

- Keep API contracts aligned with the [dashboard](../dashboard/AGENTS.md).
  Database changes also affect [workers](../workers/AGENTS.md); commit migrations
  and regenerate both clients.
- Workflow execution returns `202` after persistence, not after completion.
  Preserve run IDs, persisted terminal state, step output, and notifications.
  Managed background execution is not a crash-recoverable task queue.
- Keep manual sub-agent trials ephemeral and preserve callback-token/job-ID
  correlation, including the `_eye` envelope and legacy `_switch` compatibility.
- Preserve schedule occurrence deduplication and server-local, minute-precision
  time semantics. Review timezone or recurrence changes across both schedulers.
- Command steps are opt-in and run with the Eye host's OS permissions, not in a
  sandbox. Preserve authoring-token checks, timeout/process-tree cleanup, output
  limits, and secret exclusion. The token does not secure every API endpoint.
- Preserve worker skips as a separate outcome and do not describe registered
  workers as necessarily online or buffered logs as live streaming.
