import os

import pytest

os.environ["SCHEDULER_REGISTER_WINDOWS_TASKS"] = "false"
os.environ["SCHEDULER_POLL_SECONDS"] = "3600"


@pytest.fixture(scope="session")
def client():
    if os.getenv("RUN_DATABASE_TESTS") != "1":
        pytest.skip("Set RUN_DATABASE_TESTS=1 with PostgreSQL running")

    from fastapi.testclient import TestClient

    from app import app as app_module

    async def idle_monitor(stop_event, manager):
        await stop_event.wait()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(app_module, "schedule_monitor", idle_monitor)
        with TestClient(app_module.app) as test_client:
            yield test_client
