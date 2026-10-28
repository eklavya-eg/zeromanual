# Switch Dashboard

Responsive Next.js operations UI for building, scheduling, and observing detachable sub-agent workflows.

## Included screens

- Overview metrics, seven-day execution chart, upcoming schedules, and recent runs.
- Sub-agent catalog with create/edit forms and an interactive JSON payload trial console.
- Workflow catalog and three-panel ordered stack/payload builder.
- Exact-time and time-range schedule creation and editing.
- Run history with filters and step-level run detail.
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
NEXT_PUBLIC_SWITCH_API_URL=http://127.0.0.1:8000
```

The Switch API allows `http://localhost:3000` and `http://127.0.0.1:3000` by default. Configure additional origins with `DASHBOARD_ORIGINS` in the Switch service.

## Validate

```powershell
npm run lint
npm run build
```
