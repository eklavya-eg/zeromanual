import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl

BASE_DIR = Path(__file__).resolve().parents[1]


class RetryPolicy(BaseModel):
    strategy: Literal["fixed", "exponential"] = "exponential"
    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_delay_seconds: float = Field(default=2, ge=0, le=300)
    max_delay_seconds: float = Field(default=30, ge=0, le=900)


class Settings(BaseModel):
    broker_url: str = "redis://127.0.0.1:6379/1"
    browser_agent_url: HttpUrl = "http://127.0.0.1:8001/invoke"
    worker_queue: str = Field(default="job-applications", min_length=1)
    llm_provider: Literal["openai", "openrouter"] = "openrouter"
    llm_model: str = "nvidia/nemotron-3.5-super-vl:free"


def load_settings() -> Settings:
    load_dotenv(BASE_DIR / ".env")
    provider = os.getenv("LLM_PROVIDER", "openrouter")
    return Settings(
        broker_url=os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/1"),
        browser_agent_url=os.getenv("BROWSER_AGENT_URL", "http://127.0.0.1:8001/invoke"),
        worker_queue=os.getenv("WORKER_QUEUE", "job-applications"),
        llm_provider=provider,
        llm_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini") if provider == "openai" else os.getenv(
            "OPENROUTER_MODEL", "nvidia/nemotron-3.5-super-vl:free"
        ),
    )
