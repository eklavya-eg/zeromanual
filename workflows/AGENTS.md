# Workflows

[Repository map](../AGENTS.md) | [Setup and pipeline details](README.md)

## Purpose

This Python project contains simple executable automation pipelines, not a web
server or scheduler. Eye can schedule them through local command steps.

The current pipeline browses Naukri recommendations, extracts observed job
listings using structured LLM output, filters titles, and publishes one Celery
application task per selected job. It discovers jobs; it does not submit
applications itself.

## Code map

- [workflows/crawl_naukri.py](workflows/crawl_naukri.py): request/result models,
  browser navigation and polling, extraction, filtering, publishing, and CLI.
- [workflows/settings.py](workflows/settings.py): environment configuration and
  retry policy.
- [workflows/utils/llm.py](workflows/utils/llm.py) and
  [workflows/utils/retry.py](workflows/utils/retry.py): structured LLM and retry
  helpers.
- [tests](tests/): mocked pipeline tests and an opt-in Redis publishing test.
- [pyproject.toml](pyproject.toml): dependencies and the `crawl-naukri` entrypoint.

## Commands

Run from this directory after configuring a private environment as described in
the README:

```powershell
uv sync
uv run pytest -q
```

To intentionally run the live pipeline:

```powershell
uv run crawl-naukri
uv run crawl-naukri --config .\crawl.json
```

The optional config file must exist. Live runs need Browser Agent, Redis, and
LLM credentials; a running worker consumes the published jobs immediately.

## Change boundaries

- Keep `workers.apply_to_job`, `CELERY_BROKER_URL`, and `WORKER_QUEUE` compatible
  with the [workers project](../workers/AGENTS.md). Publish Celery messages, not
  raw JSON pushed onto a Redis list. This producer does not need Prisma or
  imports from the workers package.
- Preserve company, title, URL, package, and platform metadata. Use observed
  salary data or `NA`, never invented pay or currency conversions.
- Reuse the crawl's browser session ID and distinguish accepted/queued
  instructions from completed results. Browser polling must respect deadlines
  and instruction/session correlation.
- Do not blindly replay browser POSTs or partially acknowledged publishing.
  Failures must remain visible through errors and nonzero CLI exit status.
- Job identity claims across runs belong to workers; extraction deduplication
  is not a guarantee against repeated application submission.
