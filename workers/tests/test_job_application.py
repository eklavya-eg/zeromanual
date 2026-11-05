import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from workers.handlers.job_application import JobApplicationWorker, StepFailedError
from workers.retry import RetryExhaustedError
from workers.schemas import Resume, ResumeTailoringResult
from workers.settings import JobApplicationPayload, RetryPolicy, Settings

JOB_DESCRIPTION = "A backend engineering role using Python and PostgreSQL."


def payload(**overrides) -> JobApplicationPayload:
    return JobApplicationPayload(
        **{
            "job_url": "https://example.com/jobs/1",
            "job_title": "Backend Engineer",
            "company_name": "Example Company",
            "retry": RetryPolicy(initial_delay_seconds=0),
            **overrides,
        }
    )


def mock_browser_http(monkeypatch, handler) -> None:
    client_class = httpx.Client
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "workers.handlers.job_application.httpx.Client",
        lambda **kwargs: client_class(transport=transport, **kwargs),
    )


class FakeObservability:
    def __init__(self) -> None:
        self.entries: list[tuple[str, str, str]] = []

    def add(self, level: str, step: str, message: str, details=None) -> None:
        self.entries.append((level, step, message))

    def retry(self, step: str, attempt: int, delay: float, exc: Exception) -> None:
        self.entries.append(("warning", step, str(exc)))


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="postgresql://unused",
        broker_url="redis://unused",
        result_backend="redis://unused",
        browser_agent_url="http://browser-agent/invoke",
        worker_name="test-worker",
        worker_queue="test",
        profile_path=tmp_path / "profile.yaml",
        resume_path=tmp_path / "resume.json",
        output_dir=tmp_path / "output",
        llm_provider="openai",
        llm_model="test",
    )


@pytest.mark.parametrize("update_required", [False, True])
def test_complete_task_runs_modular_steps(monkeypatch, tmp_path: Path, update_required: bool) -> None:
    original = Resume(name="Candidate", summary="Backend engineer")
    tailored = original.model_copy(update={"summary": "Python backend engineer"})
    (tmp_path / "profile.yaml").write_text("identity:\n  full_name: Candidate\n", encoding="utf-8")
    (tmp_path / "resume.json").write_text(original.model_dump_json(), encoding="utf-8")
    observability = FakeObservability()
    browser_calls = []
    rendered = []

    def generate(**kwargs):
        assert kwargs["schema"] is ResumeTailoringResult
        assert JOB_DESCRIPTION in kwargs["prompt"]
        assert len(browser_calls) == 1
        return ResumeTailoringResult(
            update_required=update_required,
            reason="Relevant experience",
            resume=tailored if update_required else None,
        )

    def render(json_path, pdf_path, html_path):
        rendered.append(Resume.model_validate_json(json_path.read_text(encoding="utf-8")))
        pdf_path.write_bytes(b"test-pdf")
        html_path.write_text("test-html", encoding="utf-8")

    def browser(request):
        body = json.loads(request.content)
        browser_calls.append(body)
        if len(browser_calls) == 1:
            assert "Do not apply" in body["task"]
            assert "Backend Engineer" in body["task"]
            assert "Example Company" in body["task"]
            assert "https://example.com/jobs/1" in body["task"]
            assert not rendered
            assert not body.get("available_file_paths")
            result = JOB_DESCRIPTION
        else:
            assert len(rendered) == 1
            assert len(body["available_file_paths"]) == 1
            assert Path(body["available_file_paths"][0]).is_file()
            result = "submitted"
        return httpx.Response(200, json={"id": body["id"], "status": "completed", "result": result})

    worker = JobApplicationWorker(settings(tmp_path), observability, llm=SimpleNamespace(generate=generate))
    monkeypatch.setattr("workers.handlers.job_application.render", render)
    mock_browser_http(monkeypatch, browser)

    result = worker.run(payload(), "run-1")

    assert result.status == "succeeded"
    assert result.resume_updated is update_required
    assert rendered == [tailored if update_required else original]
    assert result.browser_result["result"] == "submitted"
    assert len(browser_calls) == 2
    assert browser_calls[0]["id"] == browser_calls[1]["id"] == result.browser_session_id
    assert UUID(result.browser_session_id).version == 4
    assert UUID(result.resume_id).version == 4
    assert result.resume_id != result.browser_session_id
    assert result.resume_id in result.resume_path
    assert result.resume_id in browser_calls[1]["task"]
    assert result.resume_path in browser_calls[1]["task"]
    assert browser_calls[1]["available_file_paths"] == [result.resume_path]
    assert "only when the application requires a separate" in browser_calls[1]["task"]
    assert "option to upload a different resume" in browser_calls[1]["task"]
    assert "never search for or substitute" in browser_calls[1]["task"]
    assert Path(result.resume_path).read_bytes() == b"test-pdf"
    assert [entry[1] for entry in observability.entries if entry[2] == "Step succeeded"] == [
        "load_profile",
        "load_resume",
        "fetch_job_description",
        "tailor_resume",
        "select_resume",
        "render_resume",
        "build_browser_task",
        "apply_to_job",
    ]


def test_payload_only_requires_job_metadata() -> None:
    value = payload()
    assert "job_description" not in value.model_dump()
    for field in ("job_title", "company_name", "job_url"):
        data = value.model_dump()
        del data[field]
        with pytest.raises(ValidationError):
            JobApplicationPayload.model_validate(data)
    for field in ("job_title", "company_name"):
        with pytest.raises(ValidationError):
            payload(**{field: "   "})


@pytest.mark.parametrize("description", [None, "", "   ", "Not found", {"text": JOB_DESCRIPTION}, "x" * 50_001])
def test_invalid_job_description_stops_before_tailoring(monkeypatch, tmp_path: Path, description) -> None:
    worker = JobApplicationWorker(settings(tmp_path), FakeObservability(), llm=SimpleNamespace())
    calls = []
    monkeypatch.setattr(worker, "load_profile", lambda path: {})
    monkeypatch.setattr(worker, "load_resume", lambda path: Resume(name="Candidate"))

    def browser(**kwargs):
        calls.append(kwargs)
        return {"status": "completed", "result": description}

    monkeypatch.setattr(worker, "invoke_browser_agent", browser)
    with pytest.raises(StepFailedError) as exc:
        worker.run(payload(), "run-1")
    assert exc.value.step == "fetch_job_description"
    assert len(calls) == 1
    assert not worker.settings.output_dir.exists()


def test_concurrent_runs_isolate_browser_sessions_and_resume_artifacts(monkeypatch, tmp_path: Path) -> None:
    worker = JobApplicationWorker(
        settings(tmp_path),
        FakeObservability(),
        llm=SimpleNamespace(generate=lambda **kwargs: ResumeTailoringResult(
            update_required=False, reason="Already relevant", resume=None
        )),
    )
    monkeypatch.setattr(worker, "load_profile", lambda path: {})
    monkeypatch.setattr(worker, "load_resume", lambda path: Resume(name="Candidate"))

    def render(json_path, pdf_path, html_path):
        pdf_path.write_bytes(json_path.read_bytes())
        html_path.write_text("test-html", encoding="utf-8")

    def browser(**kwargs):
        return {"status": "completed", "result": JOB_DESCRIPTION, "id": kwargs["session_id"]}

    monkeypatch.setattr("workers.handlers.job_application.render", render)
    monkeypatch.setattr(worker, "invoke_browser_agent", browser)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: worker.run(payload(), "same-run"), range(2)))
    assert results[0].browser_session_id != results[1].browser_session_id
    assert results[0].resume_id != results[1].resume_id
    assert results[0].resume_path != results[1].resume_path
    for result in results:
        assert Path(result.resume_path).is_file()
        assert Resume.model_validate_json(Path(result.resume_path).read_bytes()).name == "Candidate"


def test_resume_uuid_collision_does_not_overwrite_existing_files(monkeypatch, tmp_path: Path) -> None:
    worker = JobApplicationWorker(settings(tmp_path), FakeObservability(), llm=SimpleNamespace())
    resume_dir = worker.settings.output_dir / "run-1" / "existing-resume-id"
    resume_dir.mkdir(parents=True)
    pdf_path = resume_dir / "resume.pdf"
    pdf_path.write_bytes(b"existing-resume")
    monkeypatch.setattr("workers.handlers.job_application.render", lambda *args: pytest.fail("Must not render"))
    with pytest.raises(FileExistsError):
        worker.render_resume(Resume(name="Candidate"), "run-1", "existing-resume-id")
    assert pdf_path.read_bytes() == b"existing-resume"
    assert not (resume_dir / "resume.json").exists()


@pytest.mark.parametrize("agent_url", ["http://browser-agent/invoke", "http://browser-agent/browser/invoke"])
def test_browser_agent_waits_for_queued_instruction_without_resubmitting(
    monkeypatch, tmp_path: Path, agent_url: str
) -> None:
    config = settings(tmp_path).model_copy(update={"browser_agent_url": agent_url})
    worker = JobApplicationWorker(config, FakeObservability(), llm=SimpleNamespace())
    session_id = "a174dc08-856c-4cb8-9fa0-f68700f451b5"
    task_id = "b174dc08-856c-4cb8-9fa0-f68700f451b5"
    calls = []

    def browser(request):
        calls.append(request)
        if request.method == "POST":
            assert json.loads(request.content)["id"] == session_id
            return httpx.Response(202, json={"status": "queued", "task_id": task_id, "id": session_id})
        assert str(request.url) == f"{agent_url.rsplit('/', 1)[0]}/instructions/{task_id}"
        if len(calls) == 2:
            raise httpx.ReadTimeout("Polling timed out", request=request)
        if len(calls) == 3:
            return httpx.Response(200, json={"status": "running", "id": session_id})
        return httpx.Response(200, json={
            "status": "completed", "id": session_id,
            "response": {"status": "completed", "result": JOB_DESCRIPTION, "id": session_id},
        })

    mock_browser_http(monkeypatch, browser)
    monkeypatch.setattr("workers.handlers.job_application.time.sleep", lambda delay: None)
    result = worker.invoke_browser_agent(task="Read the description", payload=payload(), session_id=session_id)
    assert result["result"] == JOB_DESCRIPTION
    assert [request.method for request in calls] == ["POST", "GET", "GET", "GET"]


@pytest.mark.parametrize("response", [
    {"status": "failed", "errors": ["Unable to open job"]},
    {"status": "unexpected"},
    {"status": "completed", "id": "another-session"},
    ["not an object"],
])
def test_browser_agent_rejects_failed_or_invalid_responses(monkeypatch, tmp_path: Path, response) -> None:
    worker = JobApplicationWorker(settings(tmp_path), FakeObservability(), llm=SimpleNamespace())
    mock_browser_http(monkeypatch, lambda request: httpx.Response(200, json=response))
    with pytest.raises((RuntimeError, ValueError)):
        worker.invoke_browser_agent(task="Read description", payload=payload(), session_id="session-1")


def test_browser_agent_does_not_replay_submission_after_read_timeout(monkeypatch, tmp_path: Path) -> None:
    worker = JobApplicationWorker(settings(tmp_path), FakeObservability(), llm=SimpleNamespace())
    calls = []

    def browser(request):
        calls.append(request)
        raise httpx.ReadTimeout("Response lost after submitting", request=request)

    mock_browser_http(monkeypatch, browser)
    with pytest.raises(httpx.ReadTimeout):
        worker.invoke_browser_agent(task="Apply to job", payload=payload(), session_id="session-1")
    assert len(calls) == 1


@pytest.mark.parametrize("failure_step", ["fetch_job_description", "render_resume", "apply_to_job"])
def test_terminal_step_failure_stops_pipeline(monkeypatch, tmp_path: Path, failure_step: str) -> None:
    worker = JobApplicationWorker(
        settings(tmp_path),
        FakeObservability(),
        llm=SimpleNamespace(generate=lambda **kwargs: ResumeTailoringResult(
            update_required=False, reason="Already relevant", resume=None
        )),
    )
    monkeypatch.setattr(worker, "load_profile", lambda path: {})
    monkeypatch.setattr(worker, "load_resume", lambda path: Resume(name="Candidate"))
    browser_calls = []

    def browser(request):
        body = json.loads(request.content)
        browser_calls.append(body)
        if failure_step == "fetch_job_description" or len(browser_calls) == 2:
            return httpx.Response(200, json={
                "status": "failed", "id": body["id"], "errors": ["Job unavailable"],
            })
        return httpx.Response(200, json={
            "status": "completed", "result": JOB_DESCRIPTION, "id": body["id"],
        })

    def render(json_path, pdf_path, html_path):
        if failure_step == "render_resume":
            raise RuntimeError("Rendering failed")
        pdf_path.write_bytes(b"test-pdf")

    mock_browser_http(monkeypatch, browser)
    monkeypatch.setattr("workers.handlers.job_application.render", render)
    with pytest.raises(StepFailedError) as exc:
        worker.run(payload(), "run-1")
    assert exc.value.step == failure_step
    assert len(browser_calls) == (2 if failure_step == "apply_to_job" else 1)


@pytest.mark.parametrize("record", [
    {"status": "failed", "error": "Browser crashed", "response": None},
    {"status": "failed", "response": {"status": "failed", "errors": ["Job closed"]}},
    {"status": "unexpected"},
    {"status": "running", "id": "wrong-session"},
])
def test_queued_browser_failures_are_not_treated_as_success(monkeypatch, tmp_path: Path, record) -> None:
    worker = JobApplicationWorker(settings(tmp_path), FakeObservability(), llm=SimpleNamespace())
    calls = []

    def browser(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(202, json={
                "status": "accepted", "id": "session-1",
                "task_id": "b174dc08-856c-4cb8-9fa0-f68700f451b5",
            })
        return httpx.Response(200, json={"id": "session-1", **record})

    mock_browser_http(monkeypatch, browser)
    with pytest.raises((RuntimeError, ValueError)):
        worker.invoke_browser_agent(task="Apply", payload=payload(), session_id="session-1")
    assert [request.method for request in calls] == ["POST", "GET"]


def test_queued_browser_instruction_has_a_bounded_wait(monkeypatch, tmp_path: Path) -> None:
    worker = JobApplicationWorker(settings(tmp_path), FakeObservability(), llm=SimpleNamespace())
    calls = []
    ticks = iter([0, 0, 601, 601])
    monkeypatch.setattr("workers.handlers.job_application.time", SimpleNamespace(
        monotonic=lambda: next(ticks), sleep=lambda delay: None
    ))

    def browser(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(202, json={
                "status": "queued", "id": "session-1",
                "task_id": "b174dc08-856c-4cb8-9fa0-f68700f451b5",
            })
        return httpx.Response(200, json={"status": "running", "id": "session-1"})

    mock_browser_http(monkeypatch, browser)
    with pytest.raises(TimeoutError, match="Timed out waiting"):
        worker.invoke_browser_agent(task="Apply", payload=payload(), session_id="session-1")
    assert [request.method for request in calls] == ["POST", "GET"]


def test_browser_agent_retries_connection_failures(monkeypatch, tmp_path: Path) -> None:
    worker = JobApplicationWorker(settings(tmp_path), FakeObservability(), llm=SimpleNamespace())
    calls = []

    def browser(request):
        calls.append(request)
        raise httpx.ConnectError("Could not connect", request=request)

    mock_browser_http(monkeypatch, browser)
    with pytest.raises(RetryExhaustedError):
        worker.invoke_browser_agent(task="Read description", payload=payload(), session_id="session-1")
    assert len(calls) == 3
