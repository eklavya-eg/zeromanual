import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import ValidationError

from workflows.crawl_naukri import CrawlNaukri, CrawlNaukriPayload, CrawledJobsResponse, JOB_APPLICATION_TASK
from workflows.settings import Settings


def crawler(handler=None, **config):
    return CrawlNaukri(
        {"retry": {"max_attempts": 2, "initial_delay_seconds": 0, "max_delay_seconds": 0}, **config},
        settings=Settings(browser_agent_url="http://browser.test/prefix/invoke", worker_queue="test-jobs"),
        transport=httpx.MockTransport(handler) if handler else None,
    )


def completed(session_id, result="Observed listings"):
    return {"id": session_id, "status": "completed", "result": result, "errors": []}


def test_configuration_has_real_values_and_supports_legacy_breadcrumb_alias():
    payload = CrawlNaukriPayload(bredcrumb_visits=["Handpicked for you"], max_browser_steps=12)
    assert payload.breadcrumb_visits == ["Handpicked for you"]
    assert payload.max_browser_steps == 12
    assert isinstance(payload.retry.max_attempts, int)
    assert CrawlNaukriPayload(breadcrumb_visits=[]).breadcrumb_visits == []
    for config in [{"max_browser_steps": 0}, {"breadcrumb_visits": ["  "]}, {"unknown": True}, {"browser_timeout_seconds": 0}]:
        with pytest.raises(ValidationError):
            CrawlNaukriPayload.model_validate(config)


def test_direct_invocation_sends_uuid_steps_and_uses_completed_result():
    session_id = str(uuid4())
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=completed(session_id))

    result = crawler(handler, max_browser_steps=12).invoke_browser_agent(task="Read jobs", session_id=session_id)
    assert result["result"] == "Observed listings"
    assert len(seen) == 1
    assert seen[0].url.path == "/prefix/invoke"
    assert json.loads(seen[0].content) == {"task": "Read jobs", "id": session_id, "max_steps": 12}


@pytest.mark.parametrize("initial_status", ["accepted", "queued"])
def test_queued_invocation_polls_correct_instruction_and_keeps_prefix(initial_status):
    session_id, instruction_id = str(uuid4()), str(uuid4())
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(202, json={"id": session_id, "task_id": instruction_id, "status": initial_status})
        assert request.url.path == f"/prefix/instructions/{instruction_id}"
        status = "running" if len(requests) == 2 else "completed"
        return httpx.Response(200, json={
            "id": session_id, "task_id": instruction_id, "status": status,
            "response": completed(session_id) if status == "completed" else None,
        })

    result = crawler(handler, poll_interval_seconds=0.001).invoke_browser_agent(task="Read", session_id=session_id)
    assert result["status"] == "completed"
    assert [request.method for request in requests] == ["POST", "GET", "GET"]


@pytest.mark.parametrize("record", [
    {"status": "failed", "error": "Browser failed", "response": {"status": "completed"}},
    {"status": "completed", "response": None},
    {"status": "unexpected"},
    {"status": "completed", "id": str(uuid4())},
    {"status": "completed", "task_id": str(uuid4())},
])
def test_failed_or_mismatched_instruction_never_becomes_success(record):
    session_id, instruction_id = str(uuid4()), str(uuid4())

    def handler(request):
        if request.method == "POST":
            return httpx.Response(202, json={"id": session_id, "task_id": instruction_id, "status": "queued"})
        return httpx.Response(200, json={"id": session_id, "task_id": instruction_id, "response": completed(session_id), **record})

    with pytest.raises((RuntimeError, ValueError)):
        crawler(handler).invoke_browser_agent(task="Read", session_id=session_id)


@pytest.mark.parametrize("value", [[], {"status": "completed", "id": str(uuid4())}, {"status": "failed", "errors": ["login"]}, {"status": "running"}])
def test_invalid_direct_browser_responses_are_rejected(value):
    with pytest.raises((RuntimeError, ValueError)):
        crawler(lambda request: httpx.Response(200, json=value)).invoke_browser_agent(task="Read", session_id=str(uuid4()))


def test_browser_post_read_timeout_is_not_replayed_but_connection_errors_retry():
    session_id = str(uuid4())
    attempts = []

    def ambiguous(request):
        attempts.append(request)
        raise httpx.ReadTimeout("Response lost", request=request)

    with pytest.raises(httpx.ReadTimeout):
        crawler(ambiguous).invoke_browser_agent(task="Read", session_id=session_id)
    assert len(attempts) == 1
    attempts.clear()

    def connection(request):
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.ConnectError("Not connected", request=request)
        return httpx.Response(200, json=completed(session_id))

    assert crawler(connection).invoke_browser_agent(task="Read", session_id=session_id)["status"] == "completed"
    assert len(attempts) == 2


def test_poll_get_retries_transport_errors_without_reposting():
    session_id, instruction_id = str(uuid4()), str(uuid4())
    calls = []

    def handler(request):
        calls.append(request.method)
        if request.method == "POST":
            return httpx.Response(202, json={"id": session_id, "task_id": instruction_id, "status": "queued"})
        if calls == ["POST", "GET"]:
            raise httpx.ReadError("temporary poll failure", request=request)
        return httpx.Response(200, json={
            "id": session_id, "task_id": instruction_id,
            "status": "completed", "response": completed(session_id),
        })

    assert crawler(handler).invoke_browser_agent(task="Read", session_id=session_id)["status"] == "completed"
    assert calls == ["POST", "GET", "GET"]


def test_queued_deadline_is_bounded(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("workflows.crawl_naukri.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("workflows.crawl_naukri.time.sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))
    session_id, instruction_id = str(uuid4()), str(uuid4())
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(202 if request.method == "POST" else 200, json={
            "id": session_id, "task_id": instruction_id,
            "status": "queued" if request.method == "POST" else "running",
        })

    with pytest.raises(TimeoutError):
        crawler(handler, browser_timeout_seconds=2, poll_interval_seconds=1).invoke_browser_agent(task="Read", session_id=session_id)
    assert clock[0] == 2
    assert len(calls) == 3


class FakeProducer:
    def __init__(self, fail_after=None):
        self.messages = []
        self.fail_after = fail_after

    def send_task(self, name, **kwargs):
        if self.fail_after == len(self.messages):
            raise ConnectionError("Broker unavailable")
        self.messages.append((name, kwargs))
        return SimpleNamespace(id=str(uuid4()))


class FakeLLM:
    def __init__(self, jobs):
        self.jobs = jobs
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return CrawledJobsResponse.model_validate({"jobs": self.jobs})


def job(url="https://www.naukri.com/job-listings-example-123"):
    return {"job_url": url, "job_title": " Backend Engineer ", "company_name": " Example Company ", "package": "NA"}


def test_complete_crawl_reuses_session_deduplicates_and_publishes_worker_payload(monkeypatch):
    llm = FakeLLM([job(), job("https://www.naukri.com/job-listings-example-123#top"), job("https://www.naukri.com/job-listings-example-456")])
    producer = FakeProducer()
    instance = crawler(breadcrumb_visits=["Applies", "One", "Two"], max_browser_steps=15)
    instance.llm, instance.producer = llm, producer
    browser_calls = []

    def browser(**kwargs):
        browser_calls.append(kwargs)
        return completed(kwargs["session_id"], "Observed jobs only")

    monkeypatch.setattr(instance, "invoke_browser_agent", browser)
    summary = instance.run()
    assert len(browser_calls) == 3
    assert {call["session_id"] for call in browser_calls} == {summary["session_id"]}
    UUID(summary["session_id"])
    assert summary["jobs_found"] == summary["jobs_queued"] == 2
    assert len(summary["tasks"]) == 2
    assert llm.calls[0]["schema"] is CrawledJobsResponse
    assert json.loads(llm.calls[0]["prompt"]) == ["Observed jobs only"] * 3
    for name, message in producer.messages:
        assert name == JOB_APPLICATION_TASK
        assert message["queue"] == "test-jobs"
        assert message["serializer"] == "json"
        assert message["retry"] is False
        payload = message["args"][0]
        assert payload["job_title"] == "Backend Engineer"
        assert payload["company_name"] == "Example Company"
        assert payload["max_browser_steps"] == 15
        assert "job_description" not in payload
        assert payload["package"] == "NA"
        assert payload["platform"] == "Naukri"
        assert "#" not in payload["job_url"]


@pytest.mark.parametrize("pay,expected", [(None, "NA"), ("", "NA"), ("  ", "NA"), ("n/a", "NA"), ("Not disclosed", "NA"), (" INR 12–18 LPA ", "INR 12–18 LPA")])
def test_published_metadata_keeps_inr_pay_and_platform(pay, expected):
    instance = crawler()
    instance.producer = FakeProducer()
    jobs = CrawledJobsResponse.model_validate({"jobs": [{**job(), "package": pay}]}).jobs
    instance.enqueue_jobs(jobs)
    published = instance.producer.messages[0][1]["args"][0]
    assert published["package"] == expected
    assert published["platform"] == "Naukri"
    assert published["company_name"] == "Example Company"
    assert published["job_title"] == "Backend Engineer"
    assert published["job_url"] == str(jobs[0].job_url)


def test_strict_extraction_schema_requires_package_without_unsupported_defaults():
    from workflows.utils.llm import strict_json_schema

    schema = strict_json_schema(CrawledJobsResponse)
    listing = schema["$defs"]["CrawledJobData"]
    assert set(listing["required"]) == {"company_name", "job_title", "job_url", "package"}
    assert listing["additionalProperties"] is False
    assert "default" not in listing["properties"]["package"]


def test_missing_package_defaults_to_na_without_dropping_listing():
    data = job()
    del data["package"]
    jobs = CrawledJobsResponse.model_validate({"jobs": [data]}).jobs
    assert len(jobs) == 1
    assert jobs[0].package == "NA"


def test_no_jobs_does_not_connect_to_broker():
    instance = crawler()
    assert instance.enqueue_jobs([]) == []
    assert instance.producer is None


def test_publish_error_reports_partial_success_without_replaying():
    instance = crawler()
    instance.producer = FakeProducer(fail_after=1)
    jobs = CrawledJobsResponse.model_validate({"jobs": [job(), job("https://example.com/jobs/2")]}).jobs
    with pytest.raises(RuntimeError, match="1/2 confirmed publishes"):
        instance.enqueue_jobs(jobs)
    assert len(instance.producer.messages) == 1


def test_missing_browser_crawl_output_does_not_publish(monkeypatch):
    instance = crawler(breadcrumb_visits=[])
    instance.producer = FakeProducer()
    monkeypatch.setattr(instance, "invoke_browser_agent", lambda **kwargs: completed(kwargs["session_id"], None))
    with pytest.raises(ValueError, match="without crawl output"):
        instance.run()
    assert not instance.producer.messages


def test_extraction_rejects_blank_metadata():
    llm = FakeLLM([{**job(), "company_name": "  "}])
    instance = crawler()
    instance.llm = llm
    with pytest.raises(ValidationError):
        instance.extract_jobs(["observed"])
