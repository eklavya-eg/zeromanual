# Switch

FastAPI service for durable scheduled, multi-agent workflows. Workflows execute a stack of detachable sub-agent services in order, using a fixed JSON payload for each step.

## Database and run

PostgreSQL runs from the repository-level Docker Compose stack with a persistent named volume and private network.

```powershell
Copy-Item .env.example .env
cd ..
docker compose --env-file switch/.env up -d postgres
cd switch
uv run prisma generate
uv run prisma migrate deploy
uv run python main.py
```

The API listens on `http://127.0.0.1:8000`; OpenAPI is available at `/docs`.

[Prisma schema](./prisma/schema.prisma) is the database model source of truth. Commit schema changes and generated migration SQL under `prisma/migrations/`; regenerate the async Python client after each schema change.

## Configuration

- `DATABASE_URL` — PostgreSQL connection used by Prisma.
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT` — local Compose database settings.
- `SWITCH_BASE_URL` — address placed in Windows Task Scheduler callbacks.
- `SCHEDULER_REGISTER_WINDOWS_TASKS` — set `false` to use only the in-process monitor.
- `SCHEDULER_POLL_SECONDS` — due-schedule reconciliation interval.
- `DASHBOARD_ORIGINS` — comma-separated browser origins allowed by CORS.

All schedule times use the Windows/server local timezone and minute precision. Ranges must start and end on the same day.

## API flow

### 1. Register sub-agents

```http
POST /api/scheduled/sub-agents
Content-Type: application/json

{
  "name": "browser",
  "description": "Local browser-use service",
  "invoke_url": "http://127.0.0.1:8001/invoke"
}
```

### 2. Create a workflow stack

```http
POST /api/scheduled/workflows
Content-Type: application/json

{
  "name": "daily job search",
  "steps": [
    {
      "sub_agent_id": "<browser-agent-id>",
      "payload": {"task": "Find matching jobs"}
    },
    {
      "sub_agent_id": "<notification-agent-id>",
      "payload": {"channel": "desktop"}
    }
  ]
}
```

Steps run sequentially in their listed order.

### 3. Add one or more schedules

Exact time every day:

```http
POST /api/scheduled/schedules
Content-Type: application/json

{
  "workflow_id": "<workflow-id>",
  "schedule_type": "time",
  "recurrence": "daily",
  "time_of_day": "21:00",
  "run_if_missed": true,
  "misfire_grace_minutes": 120
}
```

Monthly time range:

```http
POST /api/scheduled/schedules
Content-Type: application/json

{
  "workflow_id": "<workflow-id>",
  "schedule_type": "range",
  "recurrence": "monthly",
  "day_of_month": 15,
  "range_start": "21:00",
  "range_end": "23:00"
}
```

For yearly recurrence, provide both `month` and `day_of_month`. Add multiple schedule rows to give one workflow multiple times or ranges. Modify a schedule with `PATCH /api/scheduled/schedules/{schedule_id}`.

## Execution behavior

- A Windows task is registered for the start of every enabled schedule.
- The task calls `POST /api/scheduled/run/{workflow_id}?schedule_id={schedule_id}`.
- The in-process monitor performs the same due check at startup and periodically.
- Time schedules can catch up after downtime when `run_if_missed` is enabled and the delay is within `misfire_grace_minutes`.
- Range schedules execute when the server becomes live anywhere inside the current range.
- `(schedule_id, occurrence_key)` is unique, so the Windows callback and monitor cannot execute the same occurrence twice.
- Runs and individual step attempts are persisted for status and error tracking.

## Main endpoints

- `POST/GET/PATCH /api/scheduled/sub-agents`
- `POST /api/scheduled/sub-agents/{sub_agent_id}/invoke` — trial a payload through the registered service.
- `POST/GET /api/scheduled/workflows`
- `POST/GET/PATCH/DELETE /api/scheduled/schedules`
- `POST /api/scheduled/run/{workflow_id}`
- `GET /api/scheduled/runs`
- `GET /api/scheduled/runs/{run_id}/steps`
- `POST /api/scheduled/reconcile`

## Tests

Unit tests run without PostgreSQL. Set `RUN_DATABASE_TESTS=1` after starting Postgres and applying migrations to include the scheduled API integration test.

```powershell
uv run pytest -q
$env:RUN_DATABASE_TESTS = "1"
uv run pytest -q
```
