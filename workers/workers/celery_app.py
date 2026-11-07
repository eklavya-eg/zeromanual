from celery import Celery
from celery.signals import worker_ready

from workers.registration import register_worker
from workers.settings import load_settings

settings = load_settings()

celery_app = Celery(
    "eye-workers",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=["workers.tasks"],
)
celery_app.conf.update(
    task_default_queue=settings.worker_queue,
    task_routes={"workers.apply_to_job": {"queue": settings.worker_queue}},
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86_400,
    timezone="UTC",
    worker_redirect_stdouts=False
)


@worker_ready.connect(weak=False)
def register_worker_on_ready(sender=None, **kwargs) -> None:
    if sender is not None and getattr(sender, "app", None) is celery_app:
        register_worker(load_settings().worker_name)
