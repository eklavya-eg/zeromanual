# Eye

FastAPI service for application observability, control, and durable scheduled multi-agent workflows. Workflows execute an ordered stack of detachable sub-agent services and local commands. Agent steps receive fixed JSON payloads; command steps capture stdout, stderr, and exit status.

## Database and run

PostgreSQL runs from the repository-level Docker Compose stack with a persistent named volume and private network.

```powershell
Copy-Item .env.example .env
cd ..
docker compose --env-file eye/.env up -d postgres redis
cd eye
uv run prisma generate
uv run prisma migrate deploy
uv run python main.py
```

The API listens on `http://127.0.0.1:8000`; OpenAPI is available at `/docs`.

[Prisma schema](./prisma/schema.prisma) is the database model source of truth. Commit schema changes and generated migration SQL under `prisma/migrations/`; regenerate the async Python client after each schema change.

## Configuration

- `DATABASE_URL` — PostgreSQL connection used by Prisma.
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT` — local Compose database settings.
- `EYE_BASE_URL` — address placed in Windows Task Scheduler callbacks (`SWITCH_BASE_URL` remains a compatibility fallback).
- `SCHEDULER_REGISTER_WINDOWS_TASKS` — set `false` to use only the in-process monitor.
- `SCHEDULER_POLL_SECONDS` — due-schedule reconciliation interval.
- `DASHBOARD_ORIGINS` — comma-separated browser origins allowed by CORS.
- `REDIS_URL` — ephemeral task correlation, notification history, and Pub/Sub connection.
- `SUB_AGENT_JOB_TTL_SECONDS` — expiry for manual jobs and notification history.
- `SUB_AGENT_NOTIFICATION_LIMIT` — maximum recent manual results retained in Redis.

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

Steps run sequentially in their listed order. Existing payloads without `step_type` remain sub-agent steps.

### Command steps

A workflow may contain only commands or mix commands and sub-agents. Set `step_type` to the enum value `command` or `sub_agent`. A command has `sub_agent_id: null`—**not a random UUID**, since this field is a foreign key to a real sub-agent. Existing steps are migrated to `sub_agent` without changing their payloads or IDs.

```json
{
  "name": "Run a Python script twice a day",
  "steps": [
    {
      "step_type": "command",
      "sub_agent_id": null,
      "command": "& 'W:\\ZeroManual\\workers\\.venv\\Scripts\\python.exe' 'W:\\ZeroManual\\scripts\\daily_report.py'",
      "working_directory": "W:\\ZeroManual",
      "timeout_seconds": 900
    }
  ]
}
```

Use absolute interpreter/script paths rather than relying on an activated terminal environment. `working_directory` defaults to the Eye directory; `timeout_seconds` defaults to 300 and accepts 1–86400. Commands execute in Windows PowerShell (`-NoProfile -NonInteractive`) on Windows, or `/bin/sh` on Unix. Shell syntax is intentional. Python results should be printed to stdout (for example `print(json.dumps(result))`); Python return values are not automatically serialized.

**Enabling and authorization:** command execution is disabled by default. Set `EYE_ENABLE_COMMAND_STEPS=true` and configure a strong `EYE_COMMAND_ADMIN_TOKEN` in Eye's private environment, then restart Eye. Creating or updating a workflow that contains (or previously contained) commands requires the `X-Eye-Command-Token` header. The dashboard provides a password field for this header, keeps it only in component memory, and clears it when the builder closes. Never put the token in a public `NEXT_PUBLIC_` variable. Existing sub-agent-only workflows need no token. Command output records do not contain this header, and child processes do not inherit the token environment variable.

Commands run **on the Eye host with the service account's OS permissions**, not in a sandbox. Keep the entire dashboard/API behind trusted access control (for example Cloudflare Access); the authoring token does not protect existing schedule/run/read/delete endpoints. Anyone permitted to trigger a stored workflow can trigger its approved commands. Do not include secrets in commands or printed output. Leave the opt-in disabled on public or untrusted deployments.

After saving, attach the same daily time/range schedules used for agent workflows—e.g. one morning window and one evening window. Each step attempt stores `command`, `working_directory`, `exit_code`, `stdout`, `stderr`, `timed_out`, and truncation flags in `StepRun.response`. Each output stream is capped at 256 KiB while excess output is drained. Nonzero exit codes and timeouts fail the step/workflow, preserve captured output, and stop subsequent steps. Timeout/cancellation terminates the command process tree. Run details show this output for failed as well as successful commands. `total_sub_agents` counts only agent steps; `steps.length` is the total stack length.

Apply the new migration and regenerate clients before restarting services:

```powershell
uv run prisma migrate deploy
uv run prisma generate
```

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

## Manual invocation behavior

Manual invocations are not written to PostgreSQL. Eye creates an expiring Redis job, adds a protected `_eye` callback envelope to the payload, and returns `202 Accepted` with a task ID. The sub-agent runs in the background and posts its result to the webhook. Eye retains a bounded, expiring notification list in Redis and publishes the result to connected dashboard WebSockets.

For Browser Agent continuation, include an `id` UUID in the manual payload. The Browser Agent reuses that browser and queues instructions when it is busy; Eye accepts both `accepted` and `queued` dispatch states and keeps webhook job-ID correlation unchanged. Session TTL, queueing, and result APIs are described in the [Browser Agent guide](../browseragent/README.md#browser-continuation).

## Execution behavior

- A Windows task is registered for the start of every enabled schedule.
- The task calls `POST /api/scheduled/run/{workflow_id}?schedule_id={schedule_id}`.
- The in-process monitor performs the same due check at startup and periodically.
- Time schedules can catch up after downtime when `run_if_missed` is enabled and the delay is within `misfire_grace_minutes`.
- Range schedules execute when the server becomes live anywhere inside the current range.
- `(schedule_id, occurrence_key)` is unique, so the Windows callback and monitor cannot execute the same occurrence twice.
- Runs and individual step attempts are persisted for status and error tracking.

## Main endpoints

- `POST/GET/PATCH/DELETE /api/scheduled/sub-agents`
- `POST /api/scheduled/sub-agents/{sub_agent_id}/invoke` — queue a manual task and return its task ID.
- `POST /api/notifications/webhook` — receive a completed manual task from a sub-agent.
- `GET /api/notifications` — read recent ephemeral manual-task notifications.
- `WS /api/notifications/ws` — stream completed manual tasks to the dashboard.
- `POST/GET /api/scheduled/workflows`
- `GET/PATCH/DELETE /api/scheduled/workflows/{workflow_id}`
- `POST/GET/PATCH/DELETE /api/scheduled/schedules`
- `POST /api/scheduled/run/{workflow_id}`
- `GET /api/scheduled/runs`
- `GET /api/scheduled/runs/{run_id}/steps`
- `POST /api/scheduled/reconcile`
- `GET /api/workers` — registered Celery workers (registration is not a live heartbeat).
- `GET /api/workers/{worker_id}/dashboard` — worker details, all-time task metrics, and paginated task history; accepts `status` (`running`, `succeeded`, `failed`), `page` (default 1), and `page_size` (default 20, maximum 100). Metrics are independent of the history filter; success rate excludes running tasks and is null until a task completes.
- `GET /api/workers/runs` — worker task state and results.
- `GET /api/workers/runs/{task_run_id}` — one worker task run.
- `GET /api/workers/runs/{task_run_id}/logs` — ordered buffered step logs.

## Tests

Unit tests run without PostgreSQL. Set `RUN_DATABASE_TESTS=1` after starting Postgres and applying migrations to include the scheduled API integration test.

```powershell
uv run pytest -q
$env:RUN_DATABASE_TESTS = "1"
uv run pytest -q
```
