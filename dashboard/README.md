# Eye Dashboard

Responsive Next.js operations UI for building, scheduling, and observing detachable sub-agent workflows.

## Included screens

- Overview metrics, seven-day execution chart, upcoming schedules, and recent runs.
- Sub-agent catalog with create/edit forms and an interactive JSON payload trial console.
- Workflow catalog and three-panel builder for mixed command/sub-agent stacks. Command steps configure the shell command, working directory, and timeout; the step type selector can convert existing steps. Command workflow saves require Eye's private command admin token, entered temporarily in the builder (never stored). Enable `EYE_ENABLE_COMMAND_STEPS` on Eye as documented in the [backend guide](../eye/README.md#command-steps).
- Workflow Run buttons immediately show the accepted run UUID and a link to its output instead of waiting for a long command. Completion/failure arrives via WebSocket toast; run/step queries refresh automatically.
- Notifications combine workflow-run results with existing sub-agent callbacks. Workflow notifications link to durable Runs output; reconnects refresh recent Redis notification history.
- Exact-time and time-range schedule creation and editing.
- Run history with filters and step-level run detail, including command stdout/stderr, exit codes, timeouts, and failed-step output.
- Workers directory and per-worker dashboards with all-time metrics (including skipped tasks), paginated/status-filtered task history showing company, job title, job URL, INR package (`NA` when unavailable), and platform; task details expose the same metadata alongside payload/result inspection, step logs, and dedicated duplicate/red-flag skip reasons. Worker data comes from Eye's `/api/workers` endpoints. Workers register on Celery readiness (or via `python -m workers.registration` from the workers project), without waiting for a first task. The directory refreshes every 15 seconds; dashboards and task details refresh every 10 seconds. Buffered logs appear after task completion or failure.
- Usage charts and local infrastructure settings.

## Run locally

Start PostgreSQL and the FastAPI service first, then run the dashboard:

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. The default API is `http://127.0.0.1:8000`.

## Environment

```dotenv
NEXT_PUBLIC_EYE_API_URL=http://127.0.0.1:8000/api
```

The Eye API allows `http://localhost:3000` and `http://127.0.0.1:3000` by default. Configure additional origins with `DASHBOARD_ORIGINS` in the Eye service.

## Validate

```powershell
npm run lint
npm run build
```
