import asyncio
import os
from uuid import uuid4

import pytest

from app.session_store import SessionStore


def test_redis_session_ownership_expiry_and_instruction_records():
    if os.getenv("RUN_REDIS_TESTS") != "1":
        pytest.skip("Set RUN_REDIS_TESTS=1 with Redis running")

    async def scenario():
        store = SessionStore(
            os.getenv("BROWSER_REDIS_URL", "redis://127.0.0.1:6379/3"),
            namespace=f"test:browseragent:{uuid4()}",
        )
        session_id, instruction_id = str(uuid4()), str(uuid4())
        metadata = {
            "id": session_id, "owner": "owner-1", "status": "idle",
            "ttl_seconds": 1800, "queued_instructions": 0,
        }
        try:
            assert await store.claim(metadata, 1800)
            assert not await store.claim({**metadata, "owner": "owner-2"}, 1800)
            assert 0 < await store.redis.ttl(store.session_key(session_id)) <= 1800
            assert not await store.update({**metadata, "owner": "owner-2"}, 1800)
            assert await store.update({**metadata, "status": "working"}, 1800)
            assert (await store.get_session(session_id))["status"] == "working"
            await store.delete(session_id, "owner-2")
            assert await store.get_session(session_id) is not None
            await store.save_instruction(
                {"task_id": instruction_id, "status": "completed", "response": {"result": "ok"}},
                1800,
            )
            await store.touch_instruction(instruction_id, 1800)
            assert (await store.get_instruction(instruction_id))["status"] == "completed"
            await store.redis.pexpire(store.session_key(session_id), 1)
            await asyncio.sleep(0.05)
            assert await store.get_session(session_id) is None
            assert await store.claim({**metadata, "owner": "owner-2"}, 1800)
            await store.delete(session_id, "owner-1")
            assert (await store.get_session(session_id))["owner"] == "owner-2"
        finally:
            await store.redis.delete(
                store.session_key(session_id),
                f"{store.namespace}:instruction:{instruction_id}",
            )
            await store.close()

    asyncio.run(scenario())


def test_redis_purge_removes_all_session_records_and_preserves_other_owners():
    if os.getenv("RUN_REDIS_TESTS") != "1":
        pytest.skip("Set RUN_REDIS_TESTS=1 with Redis running")

    async def scenario():
        store = SessionStore(
            os.getenv("BROWSER_REDIS_URL", "redis://127.0.0.1:6379/3"),
            namespace=f"test:browseragent:{uuid4()}",
        )
        session_id, other_id = str(uuid4()), str(uuid4())
        metadata = {"id": session_id, "owner": "owner-1"}
        records = [
            {"id": session_id, "task_id": str(uuid4()), "status": status}
            for status in ["completed", "failed", "running", "queued"]
        ]
        unrelated = {"id": other_id, "task_id": str(uuid4()), "status": "completed"}
        try:
            assert await store.claim(metadata, 1800)
            assert await store.claim({"id": other_id, "owner": "other"}, 1800)
            for record in [*records, unrelated]:
                await store.save_instruction(record, 1800)
            assert not await store.purge(session_id, "foreign")
            assert not await store.purge(session_id, None)
            assert await store.get_session(session_id) == metadata
            for record in records:
                assert await store.get_instruction(record["task_id"]) == record
            assert await store.purge(session_id, "owner-1")
            assert await store.get_session(session_id) is None
            for record in records:
                assert await store.get_instruction(record["task_id"]) is None
            assert await store.get_instruction(unrelated["task_id"]) == unrelated
            assert await store.get_session(other_id) is not None
            assert await store.purge(session_id, None)

            # Expired metadata must not leave completed instruction history behind.
            await store.save_instruction(records[0], 1800)
            assert await store.purge(session_id, None)
            assert await store.get_instruction(records[0]["task_id"]) is None
        finally:
            keys = [key async for key in store.redis.scan_iter(match=f"{store.namespace}:*")]
            if keys:
                await store.redis.delete(*keys)
            await store.close()

    asyncio.run(scenario())
