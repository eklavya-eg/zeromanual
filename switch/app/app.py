import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import connect_database, disconnect_database
from app.routes.scheduled import router as scheduled_router
from app.scheduler import schedule_monitor


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    await connect_database()
    stop_event = asyncio.Event()
    monitor_task = asyncio.create_task(schedule_monitor(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        await monitor_task
        await disconnect_database()


app = FastAPI(title="Switch", lifespan=lifespan)

dashboard_origins = [
    origin.strip()
    for origin in os.getenv(
        "DASHBOARD_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=dashboard_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")


@api_router.get("")
async def api_root() -> dict[str, str]:
    return {"service": "switch", "status": "ready"}


api_router.include_router(scheduled_router)
app.include_router(api_router)
