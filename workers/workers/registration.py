import asyncio
import logging

from prisma import Prisma
from prisma.models import Worker

logger = logging.getLogger(__name__)


async def upsert_worker(db: Prisma, name: str) -> Worker:
    return await db.worker.upsert(
        where={"name": name},
        data={"create": {"name": name}, "update": {"enabled": True}},
    )


def register_worker(name: str) -> str:
    async def operation() -> str:
        db = Prisma()
        await db.connect()
        try:
            worker = await upsert_worker(db, name)
            return worker.id
        finally:
            await db.disconnect()

    worker_id = asyncio.run(operation())
    logger.info("Registered worker %s (%s) in Eye", name, worker_id)
    return worker_id


def main() -> None:
    from workers.settings import load_settings

    settings = load_settings()
    worker_id = register_worker(settings.worker_name)
    print(f"Registered {settings.worker_name}: {worker_id}")


if __name__ == "__main__":
    main()
