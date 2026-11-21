# Dashboard

[Repository map](../AGENTS.md) | [Setup and screen details](README.md)

## Purpose

This is the npm-managed TypeScript UI for Eye, built with Next.js App Router and
React. It provides overview metrics, sub-agent trial invocations, workflow
building, scheduling, run/command output inspection, notifications, and worker
dashboards. It consumes Eye's API; it does not own scheduling, worker execution,
or database persistence.

## Code map

- [src/app](src/app/): route pages for overview, agents, workflows, schedules,
  runs, workers, notifications, usage, and settings; shared layout and styles.
- [src/components](src/components/): application shell, reusable UI/forms,
  providers, worker task details, and notification streaming.
- [src/lib/api.ts](src/lib/api.ts): typed API calls, error handling, API base URL,
  and WebSocket URL construction.
- [src/lib/types.ts](src/lib/types.ts): contracts shared with Eye's responses.
- [src/lib/utils.ts](src/lib/utils.ts): shared presentation helpers.
- [package.json](package.json): npm scripts and dependencies;
  [package-lock.json](package-lock.json): dependency lockfile.

The UI uses TanStack Query for server data, React Hook Form/Zod for forms,
Tailwind CSS for styling, and Recharts for charts. Reuse existing patterns.

## Commands

Run from this directory:

```powershell
npm ci
npm run dev
```

The local UI runs at `http://localhost:3000`. Configure
`NEXT_PUBLIC_EYE_API_URL` as described in the README and run
[Eye](../eye/AGENTS.md) for live data. Validate changes with:

```powershell
npm run lint
npm run build
```

## Change boundaries

- Keep API calls centralized and update TypeScript contracts alongside backend
  schema changes. Preserve loading, empty, and explicit error states.
- A workflow run's `202` response means accepted, not successful. Retain the run
  ID/output link and refresh state through queries and notifications.
- Distinguish workflow-run notifications from manual sub-agent callbacks, and
  skipped worker tasks from failures. Worker registration is not a heartbeat.
- Keep command admin tokens only in temporary component memory and clear them
  when the builder closes. Never store secrets in `NEXT_PUBLIC_` variables.
- Keep the generated Next.js guidance below intact and read the installed
  version's documentation before changing framework-dependent behavior.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
