from datetime import datetime

from app.models import Schedule
from app.schedule_engine import due_occurrence


def make_schedule(**overrides) -> Schedule:
    values = {
        "id": "schedule-1",
        "workflow_id": "workflow-1",
        "schedule_type": "time",
        "recurrence": "daily",
        "time_of_day": "09:00",
        "range_start": None,
        "range_end": None,
        "day_of_month": None,
        "month": None,
        "run_if_missed": True,
        "misfire_grace_minutes": 60,
        "enabled": True,
        "created_at": datetime(2026, 1, 1),
        "modified_at": datetime(2026, 1, 1),
    }
    values.update(overrides)
    return Schedule(**values)


def test_exact_time_catches_up_within_grace() -> None:
    occurrence = due_occurrence(
        make_schedule(),
        datetime(2026, 10, 26, 9, 30),
    )

    assert occurrence is not None
    assert occurrence.key == "2026-10-26@09:00"
    assert occurrence.scheduled_for == datetime(2026, 10, 26, 9, 0)


def test_exact_time_does_not_catch_up_when_disabled() -> None:
    occurrence = due_occurrence(
        make_schedule(run_if_missed=False),
        datetime(2026, 10, 26, 9, 30),
    )

    assert occurrence is None


def test_range_runs_once_during_current_window() -> None:
    occurrence = due_occurrence(
        make_schedule(
            schedule_type="range",
            time_of_day=None,
            range_start="21:00",
            range_end="23:00",
        ),
        datetime(2026, 10, 26, 22, 15),
    )

    assert occurrence is not None
    assert occurrence.key == "2026-10-26@21:00-23:00"


def test_monthly_schedule_only_runs_on_selected_day() -> None:
    schedule = make_schedule(
        schedule_type="range",
        recurrence="monthly",
        time_of_day=None,
        range_start="21:00",
        range_end="23:00",
        day_of_month=15,
    )

    assert due_occurrence(schedule, datetime(2026, 10, 15, 22, 0)) is not None
    assert due_occurrence(schedule, datetime(2026, 10, 16, 22, 0)) is None
