# ZeroManual project map

This is the repository-wide guide. Read it first, then follow the linked
`AGENTS.md` for the project being changed. Each project owns its dependencies
and runtime; this repository is not a single Python package or npm application.

## Projects

| Project | Responsibility | Project guide |
| --- | --- | --- |
| [workflows](workflows/) | Simple executable pipelines. The current Naukri crawler discovers jobs and publishes application tasks to Celery. | [workflows/AGENTS.md](workflows/AGENTS.md) |
| [workers](workers/) | Long-running worker implementations, organized by worker type. Currently implements the job-application worker; future types belong in its handlers package. | [workers/AGENTS.md](workers/AGENTS.md) |
| [eye](eye/) | FastAPI backend for dashboard data, sub-agent registration and trial invocations, workflow execution, scheduling, notifications, and worker observability. | [eye/AGENTS.md](eye/AGENTS.md) |
| [browseragent](browseragent/) | Standalone browser automation service built on `browser-use`, with one-shot tasks and reusable browser sessions. | [browseragent/AGENTS.md](browseragent/AGENTS.md) |
| [dashboard](dashboard/) | npm-managed TypeScript, React, and Next.js UI for operating Eye. | [dashboard/AGENTS.md](dashboard/AGENTS.md) |
| [resume-template-engine](resume-template-engine/) | Supporting Python package that renders validated resume JSON into HTML and PDF for workers and standalone use. | [resume-template-engine/AGENTS.md](resume-template-engine/AGENTS.md) |

## How the projects connect

- The dashboard calls Eye's HTTP API and receives notifications over WebSockets.
- Eye stores workflow definitions, schedules, runs, and worker history in
  PostgreSQL. It invokes registered sub-agent HTTP services or runs configured
  local command steps. A command step can launch a pipeline from workflows.
- The Naukri pipeline calls Browser Agent, extracts job data with an LLM, and
  publishes `workers.apply_to_job` Celery messages through Redis.
- Workers consume those messages, use Browser Agent to read and apply to jobs,
  use the resume template engine to render resumes, and record results in the
  shared Eye database.
- Browser Agent owns live browsers and session cleanup; Redis stores session
  metadata and instruction results, not live browser objects.

Eye's stored, scheduled workflow stacks and the executable pipelines in the
[workflows project](workflows/AGENTS.md) are related but distinct concepts.

## Shared infrastructure and contracts

- [compose.yaml](compose.yaml) defines PostgreSQL and Redis, not the application
  processes. Default local ports are dashboard `3000`, Eye `8000`, and Browser
  Agent `8001`.
- Default Redis logical databases are Eye notifications `0`, Celery broker `1`,
  Celery results `2`, and Browser Agent sessions `3`; keep service settings aligned.
- [Eye's Prisma schema](eye/prisma/schema.prisma) and
  [migrations](eye/prisma/migrations/) own the shared database structure. Schema
  changes require regenerating the clients in both Eye and workers.
- Keep API schemas and the [dashboard types](dashboard/src/lib/types.ts) aligned.
  Keep workflow producer payloads compatible with worker validation and routing.
- Workers and Browser Agent must be able to access the same absolute resume
  artifact paths. Upload permissions are explicitly scoped per instruction.

## Working in this repository

- Run commands from the relevant project directory and use its own environment
  and lockfile. Python services use `uv`; the dashboard uses npm.
- Read the project's README for detailed setup. Keep credentials in private
  environment files; never copy keys, browser profile data, or candidate data
  into agent guides, logs, or test fixtures.
- Prefer focused, mocked tests. Live crawls, queued worker consumption, browser
  invocations, and scheduled commands can perform real external actions; do not
  use them as routine validation.
- Keep changes within the owning project and update directly dependent
  contracts when necessary. Do not edit virtual environments, dependency
  directories, generated clients, build output, or generated resume artifacts
  as source code.
