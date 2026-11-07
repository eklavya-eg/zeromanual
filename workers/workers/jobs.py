import asyncio
from typing import Any, TypedDict

from prisma import Prisma
from prisma.errors import UniqueViolationError
from pydantic import HttpUrl


def canonical_job_url(value: str) -> str:
    """Use domain + case-sensitive path as identity, without query, fragment or scheme."""
    url = HttpUrl(value if "://" in value else f"https://{value}")
    if url.username or url.password:
        raise ValueError("Job URLs must not contain credentials")
    host = url.host.lower()
    default_port = 80 if url.scheme == "http" else 443
    authority = host if url.port in (None, default_port) else f"{host}:{url.port}"
    key = f"{authority}{url.path or '/'}"
    if len(key) > 2048:
        raise ValueError("Canonical job URL exceeds 2048 characters")
    return key


class JobMetadata(TypedDict):
    company_name: str
    job_title: str
    package: str
    platform: str


def job_metadata(payload: dict[str, Any]) -> JobMetadata:
    def text(field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return "NA"
        value = value.strip()
        return "NA" if value.lower() in {"na", "n/a", "not disclosed", "not mentioned"} else value

    return {
        "company_name": text("company_name"),
        "job_title": text("job_title"),
        "package": text("package"),
        "platform": text("platform"),
    }


class JobApplicationStore:
    def claim(self, job_url: str, task_run_id: str, *, payload: dict[str, Any] | None = None) -> bool:
        async def operation() -> bool:
            db = Prisma()
            await db.connect()
            try:
                # The primary key makes this safe across concurrent Celery processes.
                await db.jobapplication.create(data={
                    "job_url": canonical_job_url(job_url),
                    "first_run_id": task_run_id,
                    **job_metadata(payload or {}),
                })
                return True
            except UniqueViolationError:
                return False
            finally:
                await db.disconnect()

        return asyncio.run(operation())
