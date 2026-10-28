import os

import pytest

os.environ["SCHEDULER_REGISTER_WINDOWS_TASKS"] = "false"
os.environ["SCHEDULER_POLL_SECONDS"] = "3600"


@pytest.fixture(scope="session")
def client():
    if os.getenv("RUN_DATABASE_TESTS") != "1":
        pytest.skip("Set RUN_DATABASE_TESTS=1 with PostgreSQL running")

    from fastapi.testclient import TestClient

    from app.app import app

    with TestClient(app) as test_client:
        yield test_client
