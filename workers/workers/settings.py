from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl, field_validator

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


class RetryPolicy(BaseModel):
    strategy: Literal["fixed", "exponential"] = "exponential"
    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_delay_seconds: float = Field(default=2, ge=0, le=300)
    max_delay_seconds: float = Field(default=30, ge=0, le=900)


class JobApplicationPayload(BaseModel):
    job_url: HttpUrl
    job_title: str = Field(min_length=1, max_length=500)
    company_name: str = Field(min_length=1, max_length=500)
    package: str = Field(default="NA", min_length=1, max_length=500)
    platform: str = Field(default="NA", min_length=1, max_length=160)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    profile_path: str | None = None
    resume_path: str | None = None
    max_browser_steps: int = Field(default=100, ge=1, le=500)
    
    @field_validator("job_title", "company_name", mode="before")
    @classmethod
    def strip_job_metadata(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("package", "platform", mode="before")
    @classmethod
    def normalize_optional_metadata(cls, value: Any) -> Any:
        if value is None:
            return "NA"
        if isinstance(value, str):
            value = value.strip()
            if value.lower() in {"", "na", "n/a", "not disclosed", "not mentioned"}:
                return "NA"
        return value


class Settings(BaseModel):
    database_url: str
    broker_url: str
    result_backend: str
    browser_agent_url: str
    worker_name: str
    worker_queue: str
    profile_path: Path
    resume_path: Path
    output_dir: Path
    llm_provider: Literal["openai", "openrouter"]
    llm_model: str


def _resolve(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else BASE_DIR / value


def load_settings() -> Settings:
    import os

    provider = os.getenv("LLM_PROVIDER", "openrouter")
    model = (
        os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        if provider == "openai"
        else os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3.5-super-vl:free")
    )
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        broker_url=os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/1"),
        result_backend=os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/2"),
        browser_agent_url=os.getenv("BROWSER_AGENT_URL", "http://127.0.0.1:8001/invoke"),
        worker_name=os.getenv("WORKER_NAME", "job-application-worker"),
        worker_queue=os.getenv("WORKER_QUEUE", "job-applications"),
        profile_path=_resolve(os.getenv("PROFILE_DATA_PATH", "static/profile.yaml")),
        resume_path=_resolve(os.getenv("RESUME_DATA_PATH", "static/resume.json")),
        output_dir=_resolve(os.getenv("WORKER_OUTPUT_DIR", "output")),
        llm_provider=provider,
        llm_model=model,
    )
