from types import SimpleNamespace
from uuid import uuid4

import pytest

from workers import tasks
from workers.handlers.job_application import StepFailedError
from workers.schemas import JobApplicationResult
from workers.settings import JobApplicationPayload


class FakeObservability:
    instances = []

    def __init__(self, name):
        self.entries = []
        self.finished = None
        self.instances.append(self)

    def start(self, **kwargs):
        self.started = kwargs
        return 'task-run'

    def add(self, *args):
        self.entries.append(args)

    def finish(self, **kwargs):
        self.finished = kwargs


def setup(monkeypatch, claim=True):
    FakeObservability.instances.clear()
    monkeypatch.setattr(tasks, 'load_settings', lambda: SimpleNamespace(worker_name='test-worker'))
    monkeypatch.setattr(tasks, 'ObservabilityStore', FakeObservability)
    monkeypatch.setattr(tasks, 'JobApplicationStore', lambda: SimpleNamespace(claim=lambda url, run, **kwargs: claim))
    return {'job_url': 'https://EXAMPLE.com/job/1?tracking=secret#apply', 'job_title': 'Engineer', 'company_name': 'Company'}


def call_task(data):
    return tasks.apply_to_job.apply(args=[data], task_id=str(uuid4()), throw=True).result


def test_duplicate_is_skipped_without_constructing_worker(monkeypatch):
    data = setup(monkeypatch, claim=False)
    monkeypatch.setattr(tasks, 'JobApplicationWorker', lambda *args: pytest.fail('Duplicate must not construct worker/browser/LLM'))
    result = call_task(data)
    assert result['status'] == 'skipped'
    assert result['skip_reason'] == 'duplicate'
    finalized = FakeObservability.instances[-1].finished
    assert finalized['skip_reason'] == 'duplicate'
    assert finalized['job_url'] == 'example.com/job/1'
    assert not finalized['succeeded']


def test_task_forwards_all_job_metadata_to_observability_and_ledger(monkeypatch):
    data = {**setup(monkeypatch, claim=False), 'package': 'INR 12–18 LPA', 'platform': 'Naukri'}
    claims = []

    def claim(url, run_id, **kwargs):
        claims.append(kwargs['payload'])
        return False

    monkeypatch.setattr(tasks, 'JobApplicationStore', lambda: SimpleNamespace(claim=claim))
    assert call_task(data)['status'] == 'skipped'
    saved = FakeObservability.instances[-1].started['payload']
    expected = JobApplicationPayload.model_validate(data).model_dump(mode='json')
    for field in ['company_name', 'job_title', 'job_url', 'package', 'platform']:
        assert saved[field] == claims[0][field]
        assert saved[field] == expected[field]


def test_redflag_is_finalized_as_skip_not_failure(monkeypatch):
    data = setup(monkeypatch)
    result = JobApplicationResult(task_run_id='task-run', status='skipped', skip_reason='redflag', reason='Excluded role')
    monkeypatch.setattr(tasks, 'JobApplicationWorker', lambda *args: SimpleNamespace(run=lambda *args: result))
    returned = call_task(data)
    assert returned['skip_reason'] == 'redflag'
    finalized = FakeObservability.instances[-1].finished
    assert not finalized['succeeded']
    assert finalized['skip_reason'] == 'redflag'
    assert finalized['skip_details'] == 'Excluded role'


def test_success_and_error_still_flush_observability(monkeypatch):
    data = setup(monkeypatch)
    result = JobApplicationResult(task_run_id='task-run', status='succeeded')
    monkeypatch.setattr(tasks, 'JobApplicationWorker', lambda *args: SimpleNamespace(run=lambda *args: result))
    assert call_task(data)['status'] == 'succeeded'
    assert FakeObservability.instances[-1].finished['succeeded']

    def fail(*args):
        raise StepFailedError('fetch_job_description', ValueError('Unavailable'))

    monkeypatch.setattr(tasks, 'JobApplicationWorker', lambda *args: SimpleNamespace(run=fail))
    with pytest.raises(StepFailedError):
        call_task(data)
    assert FakeObservability.instances[-1].finished['step_failed'] == 'fetch_job_description'
    assert not FakeObservability.instances[-1].finished['succeeded']
