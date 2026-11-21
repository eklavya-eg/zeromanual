# Browser Agent

[Repository map](../AGENTS.md) | [Setup and session API details](README.md)

## Purpose

This standalone FastAPI service runs browser automation through `browser-use`.
Eye, workflow pipelines, and workers invoke it over HTTP. It supports one-shot
tasks, callback-driven execution, and reusable browser sessions identified by
UUID. LLM providers are configured in the service environment.

## Code map

- [main.py](main.py): local server entrypoint, port `8001`.
- [app/app.py](app/app.py): HTTP endpoints, browser-use execution, and callbacks.
- [app/schemas.py](app/schemas.py): invocation, result, and callback contracts.
- [app/llm.py](app/llm.py): provider/model selection and configuration validation.
- [app/sessions.py](app/sessions.py): live browser registry, FIFO instruction
  queues, ownership, idle TTL, and termination.
- [app/session_store.py](app/session_store.py): Redis metadata and results.
- [app/browsers.py](app/browsers.py): isolated profile creation and browser cleanup.
- [tests](tests/): fake-browser/LLM tests and opt-in Redis integration coverage.
  [app/test.py](app/test.py) is a manual Chrome launcher, not the unit-test suite.

## Commands

Run from this directory after configuring a private environment:

```powershell
uv sync
uv run pytest -q
uv run python main.py
```

The service exposes `/health`, `/docs`, `POST /invoke`,
`GET /instructions/{task_id}`, and `GET`/`DELETE /sessions/{id}`. Session mode
requires Redis; one-shot requests without an `id` do not. Real invocations
require a usable browser and configured LLM credentials.

## Change boundaries

- Keep one Uvicorn process for the local browser registry. Redis stores metadata,
  not transferable browsers or restart-recoverable instruction queues.
- Without `id`, retain one-shot behavior. With `id`, reuse browser context while
  creating a fresh Agent per instruction; do not imply conversation restoration.
- Distinguish accepted/queued responses from completion. Preserve callback job
  IDs, separate instruction IDs, and `_eye`/legacy `_switch` compatibility for
  [Eye](../eye/AGENTS.md).
- Keep per-instruction `available_file_paths` explicit. A path mentioned in a
  prompt is not upload authorization, and permissions must not leak into later
  instructions or another worker's session.
- Use isolated writable profile copies for sessions. Preserve idle expiry,
  shutdown cleanup, and explicit deletion of browser/profile/Redis records;
  report cleanup failures rather than returning false success.
- Keep tests mocked by default. Do not use a personal browser profile or real
  application submissions for routine validation.
