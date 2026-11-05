import json
from typing import Any

from redis.asyncio import Redis

# Updates and deletion must never overwrite another process's browser ownership.
UPDATE_OWNED = """
local current = redis.call('GET', KEYS[1])
if not current or cjson.decode(current).owner ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
return 1
"""
DELETE_OWNED = """
local current = redis.call('GET', KEYS[1])
if not current or cjson.decode(current).owner ~= ARGV[1] then return 0 end
return redis.call('DEL', KEYS[1])
"""


class SessionStore:
    def __init__(self, url: str, namespace: str = "eye:browseragent") -> None:
        self.redis = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        self.namespace = namespace

    def session_key(self, session_id: str) -> str:
        return f"{self.namespace}:session:{session_id}"

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        value = await self.redis.get(self.session_key(session_id))
        return json.loads(value) if value else None

    async def claim(self, metadata: dict[str, Any], ttl: int) -> bool:
        return bool(await self.redis.set(
            self.session_key(metadata["id"]), json.dumps(metadata), ex=ttl, nx=True
        ))

    async def update(self, metadata: dict[str, Any], ttl: int) -> bool:
        return bool(await self.redis.eval(
            UPDATE_OWNED, 1, self.session_key(metadata["id"]),
            metadata["owner"], json.dumps(metadata), ttl,
        ))

    async def delete(self, session_id: str, owner: str) -> None:
        await self.redis.eval(DELETE_OWNED, 1, self.session_key(session_id), owner)

    async def save_instruction(self, record: dict[str, Any], ttl: int) -> None:
        await self.redis.set(
            f"{self.namespace}:instruction:{record['task_id']}",
            json.dumps(record), ex=ttl,
        )

    async def get_instruction(self, task_id: str) -> dict[str, Any] | None:
        value = await self.redis.get(f"{self.namespace}:instruction:{task_id}")
        return json.loads(value) if value else None

    async def touch_instruction(self, task_id: str, ttl: int) -> None:
        await self.redis.expire(f"{self.namespace}:instruction:{task_id}", ttl)

    async def close(self) -> None:
        await self.redis.aclose()
