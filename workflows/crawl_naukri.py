import uuid
import httpx
import time
from utils.retry import retry_call
from typing import Any, Literal
from pathlib import Path
from pydantic import BaseModel, Field, HttpUrl, field_validator

class RetryPolicy(BaseModel):
    strategy: Literal["fixed", "exponential"] = "exponential"
    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_delay_seconds: float = Field(default=2, ge=0, le=300)
    max_delay_seconds: float = Field(default=30, ge=0, le=900)

class JobApplicationPayload(BaseModel):
    job_url: HttpUrl
    job_title: str = Field(min_length=1, max_length=500)
    company_name: str = Field(min_length=1, max_length=500)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    profile_path: str | None = None
    resume_path: str | None = None
    max_browser_steps: int = Field(default=100, ge=1, le=500)

    @field_validator("job_title", "company_name", mode="before")
    @classmethod
    def strip_job_metadata(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class CrawlNaukri:
    def __init__(self, config):
        self.config = config

    def run(self):
        # Implement the crawling logic here
        print("Crawling Naukri with config:", self.config)


    def invoke_browser_agent(
        self,
        *,
        task: str,
        session_id: str,
        resume_path: Path | None = None,
    ) -> dict[str, Any]:
        with httpx.Client(timeout=600) as client:
            def request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
                # Replaying a POST after a lost response could submit the application twice.
                retry_on = (
                    (httpx.TransportError,)
                    if method == "GET"
                    else (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
                )
                response = retry_call(
                    "invoke_browser_agent",
                    client.request,
                    method,
                    url,
                    policy=RetryPolicy(**self.config.get("retry", {})),
                    retry_on=retry_on,
                    on_retry=lambda attempt, delay, exc: self.observability.retry(
                        "invoke_browser_agent", attempt, delay, exc
                    ),
                    **kwargs,
                )
                response.raise_for_status()
                value = response.json()
                if not isinstance(value, dict):
                    raise ValueError("Browser agent response must be an object")
                return value

            value = request(
                "POST",
                self.settings.browser_agent_url,
                json={
                    "task": task,
                    "max_steps": payload.max_browser_steps,
                    "id": session_id,
                    "available_file_paths": [str(resume_path)] if resume_path is not None else [],
                },
            )
            if value.get("status") in {"accepted", "queued"}:
                if value.get("id") != session_id:
                    raise ValueError("Browser agent returned a different browser session")
                instruction_id = str(UUID(value["task_id"]))
                instruction_url = str(httpx.URL(self.settings.browser_agent_url).join(
                    f"instructions/{instruction_id}"
                ))
                deadline = time.monotonic() + 600
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Timed out waiting for the browser instruction")
                    record = request("GET", instruction_url, timeout=remaining)
                    if record.get("id") != session_id:
                        raise ValueError("Browser instruction belongs to a different browser session")
                    if record.get("status") in {"completed", "failed"}:
                        value = record.get("response")
                        if not isinstance(value, dict):
                            raise RuntimeError(f"Browser instruction failed: {record.get('error')}")
                        break
                    if record.get("status") not in {"queued", "running"}:
                        raise ValueError("Browser instruction returned an unexpected status")
                    time.sleep(min(1, max(0, deadline - time.monotonic())))

            if value.get("status") == "failed":
                raise RuntimeError(f"Browser agent failed: {value.get('errors')}")
            if value.get("status") != "completed":
                raise ValueError("Browser agent did not return a completed instruction")
            if value.get("id") != session_id:
                raise ValueError("Browser agent returned a different browser session")
            return value


if __name__ == "__main__":
    config = {
        # Add any necessary configuration parameters here
    }
    crawler = CrawlNaukri(config)
    crawler.run()