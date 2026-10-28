from datetime import datetime
from uuid import uuid4

from app import execution


def test_workflow_schedule_and_execution_api(client, monkeypatch) -> None:
    invocations: list[tuple[str, dict[str, object]]] = []

    async def fake_invoke(url: str, payload: dict[str, object]) -> dict[str, object]:
        invocations.append((url, payload))
        return {"accepted": True, "payload": payload}

    monkeypatch.setattr(execution, "invoke_sub_agent", fake_invoke)

    suffix = uuid4().hex
    first_agent = client.post(
        "/api/scheduled/sub-agents",
        json={
            "name": f"browser-{suffix}",
            "description": "Local browser agent",
            "invoke_url": "http://127.0.0.1:8001/invoke",
        },
    )
    second_agent = client.post(
        "/api/scheduled/sub-agents",
        json={
            "name": f"notifier-{suffix}",
            "description": "Notification agent",
            "invoke_url": "http://127.0.0.1:8002/invoke",
        },
    )
    assert first_agent.status_code == 201
    assert second_agent.status_code == 201

    workflow_response = client.post(
        "/api/scheduled/workflows",
        json={
            "name": "job search",
            "steps": [
                {
                    "sub_agent_id": first_agent.json()["id"],
                    "payload": {"task": "Find matching jobs"},
                },
                {
                    "sub_agent_id": second_agent.json()["id"],
                    "payload": {"channel": "desktop"},
                },
            ],
        },
    )
    assert workflow_response.status_code == 201
    workflow = workflow_response.json()
    assert workflow["total_sub_agents"] == 2
    assert [step["position"] for step in workflow["steps"]] == [1, 2]

    current_time = datetime.now().strftime("%H:%M")
    schedule_response = client.post(
        "/api/scheduled/schedules",
        json={
            "workflow_id": workflow["id"],
            "schedule_type": "time",
            "recurrence": "daily",
            "time_of_day": current_time,
            "run_if_missed": True,
            "misfire_grace_minutes": 10,
        },
    )
    assert schedule_response.status_code == 201
    schedule = schedule_response.json()
    assert schedule["windows_task_name"] is None
    assert schedule["registration_error"] is None

    reconcile_response = client.post("/api/scheduled/reconcile")
    assert reconcile_response.status_code == 200
    triggered_run_id = reconcile_response.json()["triggered_run_ids"][0]

    run_url = (
        f"/api/scheduled/run/{workflow['id']}"
        f"?schedule_id={schedule['id']}"
    )
    first_run = client.post(run_url)
    duplicate_run = client.post(run_url)
    assert first_run.status_code == 200
    assert duplicate_run.status_code == 200
    assert first_run.json()["status"] == "succeeded"
    assert first_run.json()["id"] == triggered_run_id
    assert duplicate_run.json()["id"] == first_run.json()["id"]
    assert [payload for _, payload in invocations] == [
        {"task": "Find matching jobs"},
        {"channel": "desktop"},
    ]

    steps = client.get(f"/api/scheduled/runs/{first_run.json()['id']}/steps")
    assert steps.status_code == 200
    assert [step["status"] for step in steps.json()] == ["succeeded", "succeeded"]

    update_response = client.patch(
        f"/api/scheduled/schedules/{schedule['id']}",
        json={
            "schedule_type": "range",
            "time_of_day": None,
            "range_start": "21:00",
            "range_end": "23:00",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["schedule_type"] == "range"
    assert update_response.json()["range_start"] == "21:00:00"

    schedules = client.get(
        "/api/scheduled/schedules",
        params={"workflow_id": workflow["id"]},
    )
    assert schedules.status_code == 200
    assert len(schedules.json()) == 1
