import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import connect_database, disconnect_database
from app.notifications import notification_store
from app.routes.notifications import router as notifications_router
from app.routes.scheduled import router as scheduled_router
from app.routes.workers import router as workers_router
from app.scheduler import schedule_monitor
from app.workflow_runs import WorkflowRunManager


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    await connect_database()
    _app.state.workflow_runs = WorkflowRunManager(notification_store)
    stop_event = asyncio.Event()
    monitor_task = asyncio.create_task(schedule_monitor(stop_event, _app.state.workflow_runs))
    try:
        yield
    finally:
        stop_event.set()
        await monitor_task
        await _app.state.workflow_runs.close()
        await notification_store.close()
        await disconnect_database()


app = FastAPI(title="Eye", lifespan=lifespan)

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
    return {"service": "eye", "status": "ready"}


api_router.include_router(scheduled_router)
api_router.include_router(notifications_router)
api_router.include_router(workers_router)
app.include_router(api_router)
