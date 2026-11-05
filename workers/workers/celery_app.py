from celery import Celery

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
)
