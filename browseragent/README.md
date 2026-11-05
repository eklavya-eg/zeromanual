# Browser Agent

Detachable FastAPI service that executes browser tasks with `browser-use`.

## Configuration

The browser runs locally and the agent can use either OpenAI or OpenRouter directly. API keys stay in the service environment and are never sent in an invocation payload.

Copy `.env.example` to `.env`, then configure one of these options:

### OpenAI

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-4.1-mini
```

### OpenRouter

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your-key
OPENROUTER_MODEL=anthropic/claude-sonnet-4
```

`LLM_PROVIDER` selects the default. A workflow may override `provider` and `model` per invocation, provided the corresponding API key exists in the service environment.

## Run

```powershell
uv run python main.py
```

The service listens on `http://127.0.0.1:8001`.

## Invoke

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8001/invoke `
  -ContentType application/json `
  -Body '{"task":"Open example.com and return the page title","max_steps":10,"provider":"openrouter","model":"anthropic/claude-sonnet-4"}'
```

Eye manual invocations include a reserved `_eye` callback envelope. In that mode, `/invoke` immediately returns an accepted task ID, executes the browser task in the background, and posts the final response to the supplied Eye webhook. The legacy `_switch` alias remains accepted. Regular workflow requests without a callback envelope keep the synchronous response contract.

## Browser continuation

`POST /invoke` accepts an optional `id` UUID. **Omitting it keeps the existing one-shot execution/cleanup behavior and does not require Redis.**

```json
{
  "id": "0dc01594-6f6b-459c-8f35-7d61ea778c22",
  "task": "Open example.com and read its title",
  "max_steps": 10
}
```

Send the same `id` with the next instruction to reuse that browser, its tabs, cookies, and current page. A missing or expired ID creates a new browser. Each instruction uses a new Agent, as in the notebook experiment; browser context continues, but the previous Agent's LLM conversation is not restored.

For file uploads, include `available_file_paths` with the exact absolute paths accessible to the browser service:

```json
{
  "id": "0dc01594-6f6b-459c-8f35-7d61ea778c22",
  "task": "Continue the application; upload this PDF only if requested.",
  "available_file_paths": ["W:\\ZeroManual\\workers\\output\\run-id\\resume-uuid\\resume.pdf"]
}
```

Paths in task text alone do not authorize browser-use uploads. This optional list defaults to empty and is passed to the Agent for that instruction only; upload permissions do not carry over between instructions. Workers supply only the current execution's UUID-isolated resume PDF. Both services need the same accessible path or a shared volume mounted at the same location.

- Local memory holds the live Browser objects (`keep_alive=True`). Redis holds UUID ownership, `idle`/`working` status, queue length, and instruction results, not browser objects.
- Each browser receives a random **1,800–3,600 second inactivity TTL**. While it is working or has queued instructions, the TTL is refreshed every 30 seconds, so execution time does not consume the idle window. Once all instructions finish (successfully or with an error), the full idle TTL starts again. Idle maintenance does not extend that deadline.
- Expired idle browsers are explicitly killed within the next cleanup cycle (up to 30 seconds), their temporary profiles removed, and their metadata released. Shutdown cancels outstanding instructions and closes all locally owned browsers.
- Browsers use separate temporary copies of `BROWSER_USER_DATA_DIR` / `BROWSER_PROFILE_DIRECTORY`, excluding locks and caches. Different UUIDs never concurrently launch Chrome against the same writable profile. The seed profile is not modified; close the seed Chrome before starting the service for a consistent copy. Chrome's OS-bound encryption can prevent copied credentials from working, so a session may require login again.
- An idle session executes immediately and returns the usual result plus `id`. A busy session returns **202** immediately and queues its instruction FIFO:

```json
{
  "id": "0dc01594-6f6b-459c-8f35-7d61ea778c22",
  "task_id": "c4d82863-5d79-4b94-9c87-f0c5bdc8fb69",
  "status": "queued"
}
```

Read `GET /instructions/{task_id}` for the queued instruction's `queued`, `running`, `completed`, or `failed` state, response, and error. `GET /sessions/{id}` reports browser state and TTL configuration. Unknown/expired lookups return 404; an invalid UUID returns 422.

Requests with `_eye` or `_switch` still deliver completion through the existing webhook, including queued requests. For session callbacks, the accepted response preserves the callback's job ID in `task_id` and also returns an `instruction_id` for the result endpoint. Eye accepts both `accepted` and `queued` dispatch responses, so webhook correlation is preserved without polling.

Run **one Uvicorn process** for this local browser registry. If an ID belongs to another process (including stale metadata after a crash), invocation returns 409 rather than attaching to the wrong browser. Use another UUID or wait for expiry; Redis does not recover live browsers or local queues after a restart. A disconnected HTTP caller does not cancel an already accepted instruction.

### Session configuration

Start the repository Redis service before using session IDs (from the repository root):

```powershell
docker compose --env-file eye\.env up -d redis
```

- `BROWSER_REDIS_URL`: session Redis database (default `redis://127.0.0.1:6379/3`). Redis failure returns 503 for session operations; one-shot calls still work.
- `BROWSER_EXECUTABLE_PATH`: Chrome executable.
- `BROWSER_USER_DATA_DIR`, `BROWSER_PROFILE_DIRECTORY`: seed profile for persistent sessions and original profile for one-shot calls.
- `BROWSER_SESSION_DATA_DIR`: temporary isolated profile directory (default `.sessions` under the service).
- `BROWSER_MAX_SESSIONS`: maximum live local browsers (default 8).
- `BROWSER_MAX_QUEUE`: maximum waiting instructions per session (default 100). Capacity limits return 429.

### Tests

Tests use fake browsers/LLMs, never real applications or live credentials:

```powershell
uv run pytest -q
# Include the isolated Redis ownership/TTL integration test when Redis is running:
$env:RUN_REDIS_TESTS = "1"
uv run pytest -q
```

Other endpoints:

- `GET /health`
- `GET /docs`
