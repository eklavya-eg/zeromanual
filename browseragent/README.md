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

Other endpoints:

- `GET /health`
- `GET /docs`
