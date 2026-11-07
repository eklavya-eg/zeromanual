import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from workers.handlers.job_application import JobApplicationWorker, StepFailedError
from workers.retry import RetryExhaustedError
from workers.schemas import Resume, ResumeTailoringResult
from test_job_application import FakeObservability, JOB_DESCRIPTION, mock_browser_http, payload, settings


@pytest.mark.parametrize("agent_url", ["http://browser-agent/invoke", "http://browser-agent/browser/invoke"])
def test_close_browser_session_uses_idempotent_delete_and_preserves_url_prefix(monkeypatch, tmp_path, agent_url):
    config = settings(tmp_path).model_copy(update={"browser_agent_url": agent_url})
    worker = JobApplicationWorker(config, FakeObservability())
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(204)

    mock_browser_http(monkeypatch, handler)
    worker.close_browser_session("session-1", payload())
    assert len(calls) == 1
    assert calls[0].method == "DELETE"
    assert str(calls[0].url) == f"{agent_url.rsplit('/', 1)[0]}/sessions/session-1"


@pytest.mark.parametrize("recovers", [True, False])
def test_close_browser_retries_transport_failures_without_resubmitting_job(monkeypatch, tmp_path, recovers):
    observability = FakeObservability()
    worker = JobApplicationWorker(settings(tmp_path), observability)
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "DELETE"
        if not recovers or len(calls) == 1:
            raise httpx.ReadTimeout("Cleanup response lost", request=request)
        return httpx.Response(204)

    mock_browser_http(monkeypatch, handler)
    if recovers:
        worker.close_browser_session("session-1", payload())
        assert len(calls) == 2
    else:
        with pytest.raises(RetryExhaustedError):
            worker.close_browser_session("session-1", payload())
        assert len(calls) == payload().retry.max_attempts
    assert any(entry[0] == "warning" and entry[1] == "close_browser_session" for entry in observability.entries)


@pytest.mark.parametrize("status", [409, 500, 503])
def test_close_browser_session_reports_unsuccessful_cleanup(monkeypatch, tmp_path, status):
    worker = JobApplicationWorker(settings(tmp_path), FakeObservability())
    mock_browser_http(monkeypatch, lambda request: httpx.Response(status))
    with pytest.raises(httpx.HTTPStatusError):
        worker.close_browser_session("session-1", payload())


@pytest.mark.parametrize("redflag", [False, True])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_run_closes_browser_on_success_or_skip_without_losing_outcome(monkeypatch, tmp_path, redflag, cleanup_fails):
    original = Resume(name="Candidate")
    observability = FakeObservability()
    worker = JobApplicationWorker(settings(tmp_path), observability, llm=SimpleNamespace(
        generate=lambda **kwargs: ResumeTailoringResult(
            is_redflag=redflag, update_required=False, reason="Decision", resume=None if redflag else original,
        )
    ))
    monkeypatch.setattr(worker, "load_profile", lambda path: {})
    monkeypatch.setattr(worker, "load_resume", lambda path: original)
    monkeypatch.setattr(worker, "render_resume", lambda *args: Path(tmp_path / "resume.pdf"))
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "DELETE":
            return httpx.Response(503 if cleanup_fails else 204)
        body = json.loads(request.content)
        return httpx.Response(200, json={
            "id": body["id"], "status": "completed", "result": JOB_DESCRIPTION,
        })

    mock_browser_http(monkeypatch, handler)
    result = worker.run(payload(), "run-1")
    assert result.status == ("skipped" if redflag else "succeeded")
    assert [request.method for request in requests] == (["POST", "DELETE"] if redflag else ["POST", "POST", "DELETE"])
    assert requests[-1].url.path == f"/sessions/{result.browser_session_id}"
    assert observability.entries[-1] == (
        "warning" if cleanup_fails else "info", "close_browser_session",
        "Browser session cleanup failed" if cleanup_fails else "Browser session closed",
    )


def test_cleanup_failure_does_not_mask_original_step_failure(monkeypatch, tmp_path):
    worker = JobApplicationWorker(settings(tmp_path), FakeObservability())
    monkeypatch.setattr(worker, "load_profile", lambda path: {})
    monkeypatch.setattr(worker, "load_resume", lambda path: Resume(name="Candidate"))
    original_error = RuntimeError("LLM failed")
    monkeypatch.setattr(worker, "fetch_job_description", lambda *args: JOB_DESCRIPTION)

    def fail_tailoring(**kwargs):
        raise original_error

    monkeypatch.setattr(worker, "tailor_resume", fail_tailoring)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    mock_browser_http(monkeypatch, handler)
    with pytest.raises(StepFailedError) as exc:
        worker.run(payload(), "run-1")
    assert exc.value.step == "tailor_resume"
    assert exc.value.cause is original_error
    assert len(calls) == 1
    assert calls[0].method == "DELETE"


def test_failure_before_session_allocation_does_not_attempt_browser_cleanup(monkeypatch, tmp_path):
    worker = JobApplicationWorker(settings(tmp_path), FakeObservability())
    closed = []
    monkeypatch.setattr(worker, "close_browser_session", lambda *args: closed.append(args))

    def fail_profile(path):
        raise ValueError("Invalid profile")

    monkeypatch.setattr(worker, "load_profile", fail_profile)
    with pytest.raises(StepFailedError, match="load_profile"):
        worker.run(payload(), "run-1")
    assert not closed
