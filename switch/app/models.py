from datetime import UTC, datetime

from prisma.models import Schedule, StepRun, SubAgent, Workflow, WorkflowRun, WorkflowStep


def utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "Schedule",
    "StepRun",
    "SubAgent",
    "Workflow",
    "WorkflowRun",
    "WorkflowStep",
    "utc_now",
]
