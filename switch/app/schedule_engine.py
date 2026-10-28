import calendar
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.models import Schedule

ON_TIME_TOLERANCE_SECONDS = int(os.getenv("SCHEDULER_ON_TIME_TOLERANCE_SECONDS", "120"))


@dataclass(frozen=True)
class DueOccurrence:
    key: str
    scheduled_for: datetime


def parse_time(value: str) -> time:
    return time.fromisoformat(value)


def _valid_date(year: int, month: int, day: int) -> date | None:
    if day > calendar.monthrange(year, month)[1]:
        return None
    return date(year, month, day)


def _previous_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _latest_recurrence_date(schedule: Schedule, now: datetime) -> date | None:
    if schedule.recurrence == "daily":
        return now.date()

    if schedule.recurrence == "monthly":
        year, month = now.year, now.month
        for _ in range(24):
            candidate = _valid_date(year, month, schedule.day_of_month or 1)
            if candidate is not None and candidate <= now.date():
                return candidate
            year, month = _previous_month(year, month)
        return None

    for year in range(now.year, now.year - 8, -1):
        candidate = _valid_date(year, schedule.month or 1, schedule.day_of_month or 1)
        if candidate is not None and candidate <= now.date():
            return candidate
    return None


def _exact_occurrence(schedule: Schedule, now: datetime) -> DueOccurrence | None:
    candidate_date = _latest_recurrence_date(schedule, now)
    if candidate_date is None or schedule.time_of_day is None:
        return None

    due_at = datetime.combine(candidate_date, parse_time(schedule.time_of_day))
    if due_at > now:
        if schedule.recurrence == "daily":
            due_at -= timedelta(days=1)
        elif schedule.recurrence == "monthly":
            year, month = _previous_month(candidate_date.year, candidate_date.month)
            for _ in range(24):
                prior = _valid_date(year, month, schedule.day_of_month or 1)
                if prior is not None:
                    due_at = datetime.combine(prior, parse_time(schedule.time_of_day))
                    break
                year, month = _previous_month(year, month)
        else:
            for year in range(candidate_date.year - 1, candidate_date.year - 9, -1):
                prior = _valid_date(year, schedule.month or 1, schedule.day_of_month or 1)
                if prior is not None:
                    due_at = datetime.combine(prior, parse_time(schedule.time_of_day))
                    break

    allowed_delay = (
        timedelta(minutes=schedule.misfire_grace_minutes)
        if schedule.run_if_missed
        else timedelta(seconds=ON_TIME_TOLERANCE_SECONDS)
    )
    if due_at <= now <= due_at + allowed_delay:
        return DueOccurrence(
            key=f"{due_at.date().isoformat()}@{schedule.time_of_day}",
            scheduled_for=due_at,
        )
    return None


def _range_occurrence(schedule: Schedule, now: datetime) -> DueOccurrence | None:
    if schedule.range_start is None or schedule.range_end is None:
        return None

    if schedule.recurrence == "monthly" and now.day != schedule.day_of_month:
        return None
    if schedule.recurrence == "yearly" and (
        now.month != schedule.month or now.day != schedule.day_of_month
    ):
        return None

    starts_at = datetime.combine(now.date(), parse_time(schedule.range_start))
    ends_at = datetime.combine(now.date(), parse_time(schedule.range_end))
    if starts_at <= now <= ends_at:
        return DueOccurrence(
            key=f"{now.date().isoformat()}@{schedule.range_start}-{schedule.range_end}",
            scheduled_for=starts_at,
        )
    return None


def due_occurrence(schedule: Schedule, now: datetime | None = None) -> DueOccurrence | None:
    if not schedule.enabled:
        return None

    current_time = now or datetime.now()
    if schedule.schedule_type == "time":
        return _exact_occurrence(schedule, current_time)
    return _range_occurrence(schedule, current_time)
