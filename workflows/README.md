# Eye Workflows

Naukri crawler → structured job extraction → Redis-backed Celery job application queue.

## How it works

1. Validate `CrawlNaukriPayload` (including retry, navigation, browser steps and deadline).
2. Generate one browser session UUID and reuse it for the initial page and every navigation instruction.
3. Accept synchronous Browser Agent results, or wait on `/instructions/{task_id}` if the browser returns `accepted`/`queued`. Verify both session and instruction IDs. Errors, invalid responses and timeouts stop the crawl.
4. Extract observed job listings using the LLM's strict `CrawledJobsResponse` JSON schema; deduplicate URLs within the crawl (ignoring fragments).
5. Publish one JSON-serialized **Celery task message** per job to `workers.apply_to_job` on `WORKER_QUEUE`. This is not a raw Redis list of JSON; the Celery worker expects the Celery message envelope.
6. Print a summary containing the browser session ID, jobs found/queued, and published task IDs. Failures exit nonzero for Eye command-step observability.

The published payload matches the current job application worker:

```json
{
  "job_url": "https://www.naukri.com/job-listings-example-123",
  "job_title": "Backend Engineer",
  "company_name": "Example Company",
  "package": "INR 12–18 LPA",
  "platform": "Naukri",
  "retry": {
    "strategy": "exponential",
    "max_attempts": 3,
    "initial_delay_seconds": 2,
    "max_delay_seconds": 30
  },
  "max_browser_steps": 100
}
```

Every Redis/Celery message includes `company_name`, `job_title`, `job_url`, `package`, and the fixed source `platform: "Naukri"`. `package` preserves observed INR salary ranges and pay periods; missing, blank, null, or undisclosed pay becomes `"NA"`. Foreign-currency conversions and salary estimates are not invented. The worker persists these fields in task history and the application ledger, and Eye displays them in worker history and details. The worker fetches the job description itself before resume tailoring/application. The crawler never submits job applications.

## Configuration and run

From this directory:

```powershell
Copy-Item .env.example .env
uv sync
uv run crawl-naukri
# Equivalent:
uv run python -m workflows.crawl_naukri
```

Set your LLM credentials privately. The crawler's `CELERY_BROKER_URL` and `WORKER_QUEUE` must match the [workers service](../workers/README.md). No database URL, Prisma client, or worker-module imports are needed by this producer. Redis, Browser Agent and the job application Celery worker must be running; queued messages remain in Redis if the worker is stopped.

Optional `--config path\crawl.json`:

```json
{
  "naukri_url": "https://www.naukri.com/mnjuser/recommendedjobs",
  "breadcrumb_visits": ["Handpicked for you", "You might like"],
  "max_browser_steps": 100,
  "browser_timeout_seconds": 600,
  "poll_interval_seconds": 1,
  "retry": {"strategy": "fixed", "max_attempts": 3, "initial_delay_seconds": 2, "max_delay_seconds": 30}
}
```

`breadcrumb_visits: []` crawls only the starting page. The original misspelling `bredcrumb_visits` is still accepted as an alias. Config values now actually control execution; ordinary class attributes are no longer Pydantic `FieldInfo` instances.

Eye command step example (use an absolute executable path):

```powershell
& 'W:\ZeroManual\workflows\.venv\Scripts\crawl-naukri.exe' --config 'W:\ZeroManual\workflows\crawl.json'
```

Set the command's working directory to this project and choose an appropriate timeout for all navigation instructions plus LLM extraction/publishing. Browser sessions are left available for continuation and closed by Browser Agent's idle TTL.

## Failure and duplicate behavior

Only connection-establishment failures retry the browser POST; ambiguous read/write timeouts do **not** replay it. Polling GET requests can safely retry transport failures, subject to the configured deadline. HTTP error statuses, failed instructions and malformed extraction fail explicitly.

Publishing uses `retry=False` to avoid blind replay after an uncertain broker acknowledgement. On failure, the error includes already-confirmed task IDs and a confirmed count; previously published tasks are not rolled back. A manual rerun can enqueue those jobs again. Deduplication is within one crawl, not across schedules or worker executions. Celery task IDs alone do not enforce exactly-once application submission.

## Tests

```powershell
uv run pytest -q
# Optional real Redis publish/decode test uses a unique temporary queue, never the worker queue:
$env:RUN_REDIS_TESTS = '1'
uv run pytest -q
```

Browser/LLM calls in tests are mocked; tests do not crawl a real account or apply to jobs.
