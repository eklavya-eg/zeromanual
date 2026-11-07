import os
from uuid import uuid4

import pytest
from kombu import Connection

from workflows.crawl_naukri import CrawlNaukri, CrawledJobData, JOB_APPLICATION_TASK
from workflows.settings import Settings


@pytest.mark.parametrize("pay", ["NA", "INR 12–18 LPA"])
def test_celery_message_is_readable_from_isolated_redis_queue(pay):
    if os.getenv("RUN_REDIS_TESTS") != "1":
        pytest.skip("Set RUN_REDIS_TESTS=1 with Redis running")
    queue_name = f"test-crawl-naukri-{uuid4().hex}"
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/1")
    instance = CrawlNaukri(settings=Settings(broker_url=broker_url, worker_queue=queue_name))
    jobs = [CrawledJobData(
        job_url="https://www.naukri.com/job-listings-test-123",
        job_title="Backend Engineer",
        company_name="Integration Test",
        package=pay,
    )]
    with Connection(broker_url) as connection:
        queue = connection.SimpleQueue(queue_name)
        try:
            published = instance.enqueue_jobs(jobs)
            message = queue.get(block=False)
            try:
                assert message.headers["task"] == JOB_APPLICATION_TASK
                assert message.headers["id"] == published[0]["task_id"]
                args, kwargs, _ = message.payload
                assert kwargs == {}
                assert args[0]["job_url"] == str(jobs[0].job_url)
                assert args[0]["job_title"] == jobs[0].job_title
                assert args[0]["company_name"] == jobs[0].company_name
                assert args[0]["package"] == pay
                assert args[0]["platform"] == "Naukri"
                assert args[0]["retry"]["max_attempts"] == 3
                message.ack()
            finally:
                if not message.acknowledged:
                    message.reject(requeue=False)
        finally:
            queue.queue.delete()
            queue.close()
