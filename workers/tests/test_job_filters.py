from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from workers.handlers.job_application import JobApplicationWorker
from workers.jobs import canonical_job_url
from workers.schemas import Resume, ResumeTailoringResult
from test_job_application import FakeObservability, JOB_DESCRIPTION, payload, settings


@pytest.mark.parametrize('value, expected', [
    ('https://WWW.Naukri.com/jobs/123?tracking=one#apply', 'www.naukri.com/jobs/123'),
    ('http://www.naukri.com/jobs/123?source=two', 'www.naukri.com/jobs/123'),
    ('www.naukri.com/jobs/123', 'www.naukri.com/jobs/123'),
    ('https://example.com', 'example.com/'),
    ('https://example.com:443/Case/Sensitive', 'example.com/Case/Sensitive'),
    ('http://example.com:8080/job?x=1', 'example.com:8080/job'),
])
def test_canonical_url(value, expected):
    assert canonical_job_url(value) == expected
    assert canonical_job_url(expected) == expected


def test_canonical_url_rejects_credentials_and_invalid_scheme():
    for url in ['https://user:password@example.com/job', 'ftp://example.com/job', '']:
        with pytest.raises(ValueError):
            canonical_job_url(url)


def test_redflag_stops_before_resume_rendering_and_application(monkeypatch, tmp_path):
    calls = []
    observability = FakeObservability()

    def generate(**kwargs):
        calls.append(kwargs)
        assert 'redflags' in kwargs['prompt']
        assert 'data scientist' in kwargs['prompt']
        assert 'Do NOT tailor' in kwargs['prompt']
        return ResumeTailoringResult(is_redflag=True, update_required=False,
                                    reason='Data scientist role is excluded by the candidate.', resume=None)

    worker = JobApplicationWorker(settings(tmp_path), observability, llm=SimpleNamespace(generate=generate))
    monkeypatch.setattr(worker, 'load_profile', lambda path: {'redflags': ['No data scientist roles']})
    monkeypatch.setattr(worker, 'load_resume', lambda path: Resume(name='Candidate'))
    browser_calls = []
    monkeypatch.setattr(worker, 'invoke_browser_agent', lambda **kwargs: browser_calls.append(kwargs) or {'result': JOB_DESCRIPTION})
    monkeypatch.setattr(worker, 'render_resume', lambda *args: pytest.fail('Must not render a red-flag resume'))
    monkeypatch.setattr(worker, 'build_browser_task', lambda **kwargs: pytest.fail('Must not prepare an application'))
    closed_sessions = []
    monkeypatch.setattr(worker, 'close_browser_session', lambda session_id, value: closed_sessions.append(session_id))

    result = worker.run(payload(job_title='Data Scientist'), 'redflag-run')
    assert closed_sessions == [result.browser_session_id]
    assert result.status == 'skipped'
    assert result.skip_reason == 'redflag'
    assert result.resume_id is result.resume_path is result.browser_result is None
    assert len(calls) == len(browser_calls) == 1
    assert not worker.settings.output_dir.exists()
    assert any(entry[1] == 'redflag' for entry in observability.entries)


@pytest.mark.parametrize('data', [
    {'is_redflag': True, 'update_required': True, 'resume': {'name': 'Candidate'}},
    {'is_redflag': True, 'update_required': False, 'resume': {'name': 'Candidate'}},
    {'is_redflag': False, 'update_required': True, 'resume': None},
    {'is_redflag': False, 'update_required': False, 'resume': None},
])
def test_invalid_llm_decisions_fail_closed(data):
    with pytest.raises(ValidationError):
        ResumeTailoringResult.model_validate({'reason': 'decision', **data})


def test_strict_llm_schema_requires_all_nested_fields_and_disallows_extras():
    from workers.llm import strict_json_schema

    schema = strict_json_schema(ResumeTailoringResult)

    def verify(node):
        if isinstance(node, dict):
            assert 'default' not in node
            if node.get('type') == 'object':
                assert node['additionalProperties'] is False
                assert set(node['required']) == set(node.get('properties', {}))
            for child in node.values():
                verify(child)
        elif isinstance(node, list):
            for child in node:
                verify(child)

    verify(schema)
    assert 'is_redflag' in schema['required']


def test_profile_rejects_malformed_redflags_before_any_llm_call(tmp_path):
    worker = JobApplicationWorker(settings(tmp_path), FakeObservability(), llm=SimpleNamespace())
    for text in ['redflags: no data jobs', 'redflags: [""]', 'redflags: [123]']:
        path = tmp_path / 'profile.yaml'
        path.write_text(text)
        with pytest.raises(ValueError, match='redflags'):
            worker.load_profile(path)


def test_nonredflag_decision_returns_complete_resume_in_one_call(tmp_path):
    calls = []
    resume = Resume(name='Candidate', summary='Original')
    updated = resume.model_copy(update={'summary': 'Python backend engineer'})
    llm = SimpleNamespace(generate=lambda **kwargs: calls.append(kwargs) or {
        'is_redflag': False, 'update_required': True, 'reason': 'Eligible backend job',
        'resume': updated.model_dump(),
    })
    worker = JobApplicationWorker(settings(tmp_path), FakeObservability(), llm=llm)
    result = worker.tailor_resume(job_description=JOB_DESCRIPTION, profile={'redflags': []}, resume=resume, payload=payload())
    assert not result.is_redflag
    assert worker.select_resume(resume, result) == updated
    assert len(calls) == 1
    assert set(calls[0]['schema'].model_json_schema()['required']) == {'is_redflag', 'update_required', 'reason', 'resume'}
