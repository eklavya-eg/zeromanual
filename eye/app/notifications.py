import json
import os
from datetime import UTC, datetime
from time import time
from typing import Any
from uuid import uuid4

from prisma.models import WorkflowRun
from redis.asyncio import Redis

JOB_TTL_SECONDS = int(os.getenv("SUB_AGENT_JOB_TTL_SECONDS", "86400"))
NOTIFICATION_LIMIT = int(os.getenv("SUB_AGENT_NOTIFICATION_LIMIT", "100"))
NOTIFICATION_CHANNEL = "eye:sub-agent-notifications"
PUBLISH_WORKFLOW = """
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
redis.call('SET', KEYS[1], '1', 'EX', ARGV[1])
redis.call('ZADD', KEYS[2], ARGV[2], ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[2], 0, tonumber(ARGV[2]) - tonumber(ARGV[1]))
redis.call('ZREMRANGEBYRANK', KEYS[2], 0, -(tonumber(ARGV[4]) + 1))
redis.call('EXPIRE', KEYS[2], ARGV[1])
redis.call('PUBLISH', KEYS[3], ARGV[3])
return 1
"""


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


class NotificationStore:
    def __init__(self, namespace: str = "eye") -> None:
        self.namespace = namespace
        self.channel = f"{namespace}:sub-agent-notifications"
        self._redis: Redis | None = None

    def client(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(
                os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=25,
            )
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def create_job(
        self,
        *,
        agent_id: str,
        agent_name: str,
        payload: dict[str, Any],
    ) -> tuple[str, str]:
        job_id = str(uuid4())
        callback_token = str(uuid4())
        job = {
            "job_id": job_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "payload": payload,
            "callback_token": callback_token,
            "created_at": utc_timestamp(),
        }
        await self.client().set(
            f"{self.namespace}:sub-agent-job:{job_id}",
            json.dumps(job),
            ex=JOB_TTL_SECONDS,
        )
        return job_id, callback_token

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        value = await self.client().get(f"{self.namespace}:sub-agent-job:{job_id}")
        return json.loads(value) if value else None

    async def remove_job(self, job_id: str) -> None:
        await self.client().delete(f"{self.namespace}:sub-agent-job:{job_id}")

    async def complete_job(
        self,
        *,
        job: dict[str, Any],
        status: str,
        response: dict[str, Any] | None,
        error: str | None,
    ) -> dict[str, Any] | None:
        job_id = str(job["job_id"])
        completion_key = f"{self.namespace}:sub-agent-job-completed:{job_id}"
        claimed = await self.client().set(
            completion_key,
            "1",
            ex=JOB_TTL_SECONDS,
            nx=True,
        )
        if not claimed:
            return None

        notification = {
            "job_id": job_id,
            "agent_id": job["agent_id"],
            "agent_name": job["agent_name"],
            "status": status,
            "payload": job["payload"],
            "response": response,
            "error": error,
            "created_at": job["created_at"],
            "completed_at": utc_timestamp(),
        }
        encoded = json.dumps(notification)
        history_key = f"{self.namespace}:sub-agent-notification-history"
        completed_at = time()
        async with self.client().pipeline(transaction=True) as pipeline:
            pipeline.delete(f"{self.namespace}:sub-agent-job:{job_id}")
            pipeline.zadd(history_key, {encoded: completed_at})
            pipeline.zremrangebyscore(history_key, 0, completed_at - JOB_TTL_SECONDS)
            pipeline.zremrangebyrank(history_key, 0, -(NOTIFICATION_LIMIT + 1))
            pipeline.expire(history_key, JOB_TTL_SECONDS)
            pipeline.publish(self.channel, encoded)
            await pipeline.execute()
        return notification

    async def publish_workflow_run(self, run: WorkflowRun, workflow_name: str) -> None:
        notification = {
            "kind": "workflow_run",
            "run_id": run.id,
            "workflow_id": run.workflow_id,
            "workflow_name": workflow_name,
            "attempt_count": run.attempt_count,
            "status": run.status,
            "error": run.error,
            "created_at": run.started_at.isoformat(),
            "completed_at": run.finished_at.isoformat() if run.finished_at else utc_timestamp(),
        }
        await self.client().eval(
            PUBLISH_WORKFLOW, 3,
            f"{self.namespace}:workflow-run-completed:{run.id}:{run.attempt_count}",
            f"{self.namespace}:sub-agent-notification-history", self.channel,
            JOB_TTL_SECONDS, time(), json.dumps(notification), NOTIFICATION_LIMIT,
        )

    async def list_notifications(self) -> list[dict[str, Any]]:
        history_key = f"{self.namespace}:sub-agent-notification-history"
        await self.client().zremrangebyscore(
            history_key,
            0,
            time() - JOB_TTL_SECONDS,
        )
        values = await self.client().zrevrange(history_key, 0, NOTIFICATION_LIMIT - 1)
        return [json.loads(value) for value in values]


notification_store = NotificationStore()
