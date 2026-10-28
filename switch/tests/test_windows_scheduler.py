from datetime import datetime

from app.models import Schedule
from app.windows_scheduler import build_schtasks_command, windows_task_name


def test_builds_daily_windows_task_command(monkeypatch) -> None:
    monkeypatch.setenv("SWITCH_BASE_URL", "http://127.0.0.1:8000")
    schedule = Schedule(
        id="schedule-1",
        workflow_id="workflow-1",
        schedule_type="range",
        recurrence="daily",
        range_start="21:00",
        range_end="23:00",
        run_if_missed=True,
        misfire_grace_minutes=60,
        enabled=True,
        created_at=datetime(2026, 1, 1),
        modified_at=datetime(2026, 1, 1),
    )

    command = build_schtasks_command(schedule)

    assert command[:4] == [
        "schtasks.exe",
        "/Create",
        "/TN",
        windows_task_name("workflow-1", "schedule-1"),
    ]
    assert "/SC" in command
    assert command[command.index("/SC") + 1] == "DAILY"
    assert command[command.index("/ST") + 1] == "21:00"
    assert "schedule_id=schedule-1" in command[command.index("/TR") + 1]


def test_builds_yearly_windows_task_as_monthly_month_filter() -> None:
    schedule = Schedule(
        id="schedule-2",
        workflow_id="workflow-1",
        schedule_type="time",
        recurrence="yearly",
        time_of_day="09:30",
        day_of_month=20,
        month=6,
        run_if_missed=True,
        misfire_grace_minutes=60,
        enabled=True,
        created_at=datetime(2026, 1, 1),
        modified_at=datetime(2026, 1, 1),
    )

    command = build_schtasks_command(schedule)

    assert command[command.index("/SC") + 1] == "MONTHLY"
    assert command[command.index("/M") + 1] == "JUN"
    assert command[command.index("/D") + 1] == "20"
