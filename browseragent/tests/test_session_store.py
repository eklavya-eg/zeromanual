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
