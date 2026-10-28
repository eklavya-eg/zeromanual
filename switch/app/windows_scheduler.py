import asyncio
import os
import sys
from dataclasses import dataclass

from app.models import Schedule

MONTH_NAMES = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)


@dataclass(frozen=True)
class TaskRegistration:
    task_name: str | None
    error: str | None


def windows_task_name(workflow_id: str, schedule_id: str) -> str:
    return f"Switch-{workflow_id}-{schedule_id}"


def build_schtasks_command(schedule: Schedule) -> list[str]:
    task_name = windows_task_name(schedule.workflow_id, schedule.id)
    trigger_time = schedule.time_of_day or schedule.range_start
    if trigger_time is None:
        raise ValueError("Schedule has no trigger time")

    base_url = os.getenv("SWITCH_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    endpoint = (
        f"{base_url}/api/scheduled/run/{schedule.workflow_id}"
        f"?schedule_id={schedule.id}"
    )
    action = (
        "powershell.exe -NoProfile -NonInteractive -Command "
        f'"try {{ Invoke-RestMethod -Method Post -Uri \'{endpoint}\' | Out-Null }} '
        'catch { exit 1 }"'
    )
    command = [
        "schtasks.exe", "/Create", "/TN", task_name, "/TR", action,
        "/ST", trigger_time, "/F",
    ]

    if schedule.recurrence == "daily":
        command.extend(["/SC", "DAILY"])
    elif schedule.recurrence == "monthly":
        command.extend(["/SC", "MONTHLY", "/D", str(schedule.day_of_month)])
    else:
        command.extend(
            [
                "/SC", "MONTHLY",
                "/M", MONTH_NAMES[(schedule.month or 1) - 1],
                "/D", str(schedule.day_of_month),
            ]
        )
    return command


async def register_windows_task(schedule: Schedule) -> TaskRegistration:
    if os.getenv("SCHEDULER_REGISTER_WINDOWS_TASKS", "true").lower() != "true":
        return TaskRegistration(task_name=None, error=None)
    if sys.platform != "win32":
        return TaskRegistration(task_name=None, error="Windows Task Scheduler is unavailable")

    command = build_schtasks_command(schedule)
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        message = (stderr or stdout).decode(errors="replace").strip()
        return TaskRegistration(task_name=None, error=message or "schtasks failed")
    return TaskRegistration(
        task_name=windows_task_name(schedule.workflow_id, schedule.id),
        error=None,
    )


async def delete_windows_task(task_name: str | None) -> None:
    if not task_name or sys.platform != "win32":
        return
    process = await asyncio.create_subprocess_exec(
        "schtasks.exe", "/Delete", "/TN", task_name, "/F",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.wait()
