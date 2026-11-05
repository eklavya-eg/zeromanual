import uuid
from uuid import UUID
import httpx
import time
from typing import Any, Literal
from pathlib import Path
from pydantic import BaseModel, Field, HttpUrl, field_validator

from utils.retry import retry_call
from utils.llm import StructuredLLM
from workers.workers.settings import load_settings

class RetryPolicy(BaseModel):
    strategy: Literal["fixed", "exponential"] = "exponential"
    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_delay_seconds: float = Field(default=2, ge=0, le=300)
    max_delay_seconds: float = Field(default=30, ge=0, le=900)

class CrawlNaukriPayload(BaseModel):
    naukri_url: HttpUrl = "https://www.naukri.com/mnjuser/recommendedjobs"
    bredcrumb_visits: list = Field(default=[
        "Applies",
        "Handpicked for you",
        "Profile",
        "Preferences",
        "You might like"
    ], min_length=1, max_length=500)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    max_browser_steps: int = Field(default=100, ge=1, le=500)

class CrawledJobData(BaseModel):
    company_name: str
    job_title: str
    job_url: HttpUrl
    package: str  # Pay in INR, or "NA" if not available

class CrawledJobsResponse(BaseModel):
    jobs: list[CrawledJobData]

class CrawlNaukri:
    def __init__(self, config):
        self.config = config
        self.naukri_url: HttpUrl = "https://www.naukri.com/mnjuser/recommendedjobs"
        self.bredcrumb_visits: list = Field(default=[
            "Applies",
            "Handpicked for you",
            "Profile",
            "Preferences",
            "You might like"
        ], min_length=1, max_length=500)
        self.retry: RetryPolicy = Field(default_factory=RetryPolicy)
        self.max_browser_steps: int = Field(default=100, ge=1, le=500)
        self.settings = load_settings()
        self.llm = StructuredLLM(provider=self.settings.llm_provider, model=self.settings.llm_model)

    def run(self):
        # Implement the crawling logic here
        print("Crawling Naukri with config:", self.config)
        uuid_str = str(uuid.uuid4())
        result = self.invoke_browser_agent(
            task=f"open {self.naukri_url} and scroll, get and return company name, job title, job url, and package (pay in INR if not available directly just return NA) in json format",
            session_id=uuid_str,
        )
        results = []
        for item in self.bredcrumb_visits:
            result_ = self.invoke_browser_agent(
                task=f"navigate to {item} from breadcrumb and scroll, get and return company name, job title, job url, and package (pay in INR if not available directly just return NA) in json format",
                session_id=uuid_str,
            )
            results.append(result_)
        results = [result] + results
        response = self.llm.generate(
            system_prompt="Extract the company name, job title, job url, and package (pay in INR if not available directly just return NA) from the following data and return it in a structured format.",
            prompt=f"{results}",
            schema=CrawledJobsResponse
        )
        jobs = response.jobs
        for job in jobs:
            pass
        return


    def invoke_browser_agent(
        self,
        *,
        task: str,
        session_id: str,
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
                    "max_steps": self.max_browser_steps,
                    "id": session_id,
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