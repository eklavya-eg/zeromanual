from typing import Any

from workers.celery_app import celery_app
from workers.handlers.job_application import JobApplicationWorker, StepFailedError
from workers.observability import ObservabilityStore
from workers.settings import JobApplicationPayload, load_settings


@celery_app.task(bind=True, name="workers.apply_to_job")
def apply_to_job(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    payload = JobApplicationPayload.model_validate(raw_payload)
    celery_task_id = str(self.request.id)
    observability = ObservabilityStore(settings.worker_name)
    task_run_id = observability.start(
        celery_task_id=celery_task_id,
        payload=payload.model_dump(mode="json"),
        job_url=str(payload.job_url),
    )
    worker = JobApplicationWorker(settings, observability)

    try:
        result = worker.run(payload, task_run_id)
    except StepFailedError as exc:
        observability.finish(
            succeeded=False,
            error=str(exc.cause)[:4_000],
            step_failed=exc.step,
        )
        raise
    except Exception as exc:
        observability.finish(
            succeeded=False,
            error=str(exc)[:4_000],
            step_failed="unhandled",
        )
        raise

    data = result.model_dump(mode="json")
    observability.finish(succeeded=True, result=data)
    return data
