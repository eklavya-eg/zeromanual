from datetime import datetime, time
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ScheduleType(StrEnum):
    TIME = "time"
    RANGE = "range"


class Recurrence(StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubAgentCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=4_000)] = ""
    invoke_url: HttpUrl
    enabled: bool = True


class SubAgentUpdate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    description: Annotated[str, Field(max_length=4_000)] | None = None
    invoke_url: HttpUrl | None = None
    enabled: bool | None = None


class SubAgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    invoke_url: str
    enabled: bool
    created_at: datetime
    modified_at: datetime


class SubAgentTrialResponse(BaseModel):
    agent_id: str
    agent_name: str
    status: str
    duration_ms: int
    result: dict[str, Any]


class WorkflowStepCreate(BaseModel):
    sub_agent_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowStepResponse(BaseModel):
    id: str
    position: int
    sub_agent_id: str
    payload: dict[str, Any]


class WorkflowCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str, Field(max_length=4_000)] = ""
    steps: Annotated[list[WorkflowStepCreate], Field(min_length=1)]
    enabled: bool = True


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str
    total_sub_agents: int
    enabled: bool
    steps: list[WorkflowStepResponse]
    created_at: datetime
    modified_at: datetime


class ScheduleFields(BaseModel):
    schedule_type: ScheduleType
    recurrence: Recurrence
    time_of_day: time | None = None
    range_start: time | None = None
    range_end: time | None = None
    day_of_month: Annotated[int | None, Field(ge=1, le=31)] = None
    month: Annotated[int | None, Field(ge=1, le=12)] = None
    run_if_missed: bool = True
    misfire_grace_minutes: Annotated[int, Field(ge=0, le=525_600)] = 1_440
    enabled: bool = True

    @model_validator(mode="after")
    def validate_schedule_shape(self) -> "ScheduleFields":
        if self.schedule_type == ScheduleType.TIME:
            if self.time_of_day is None:
                raise ValueError("time_of_day is required for a time schedule")
            if self.range_start is not None or self.range_end is not None:
                raise ValueError("range fields are only valid for a range schedule")
        else:
            if self.range_start is None or self.range_end is None:
                raise ValueError("range_start and range_end are required for a range schedule")
            if self.range_start >= self.range_end:
                raise ValueError("range_end must be later than range_start")
            if self.time_of_day is not None:
                raise ValueError("time_of_day is only valid for a time schedule")

        supplied_times = [self.time_of_day, self.range_start, self.range_end]
        if any(value is not None and (value.second or value.microsecond) for value in supplied_times):
            raise ValueError("schedule times must use minute precision")

        if self.recurrence == Recurrence.DAILY:
            if self.day_of_month is not None or self.month is not None:
                raise ValueError("daily schedules do not accept day_of_month or month")
        elif self.recurrence == Recurrence.MONTHLY:
            if self.day_of_month is None:
                raise ValueError("day_of_month is required for monthly schedules")
            if self.month is not None:
                raise ValueError("month is only valid for yearly schedules")
        elif self.day_of_month is None or self.month is None:
            raise ValueError("month and day_of_month are required for yearly schedules")

        return self


class ScheduleCreate(ScheduleFields):
    workflow_id: str


class ScheduleUpdate(BaseModel):
    schedule_type: ScheduleType | None = None
    recurrence: Recurrence | None = None
    time_of_day: time | None = None
    range_start: time | None = None
    range_end: time | None = None
    day_of_month: Annotated[int | None, Field(ge=1, le=31)] = None
    month: Annotated[int | None, Field(ge=1, le=12)] = None
    run_if_missed: bool | None = None
    misfire_grace_minutes: Annotated[int | None, Field(ge=0, le=525_600)] = None
    enabled: bool | None = None


class ScheduleResponse(BaseModel):
    id: str
    workflow_id: str
    schedule_type: ScheduleType
    recurrence: Recurrence
    time_of_day: time | None
    range_start: time | None
    range_end: time | None
    day_of_month: int | None
    month: int | None
    run_if_missed: bool
    misfire_grace_minutes: int
    enabled: bool
    windows_task_name: str | None
    registration_error: str | None
    created_at: datetime
    modified_at: datetime


class RunResponse(BaseModel):
    id: str
    workflow_id: str
    schedule_id: str | None
    occurrence_key: str | None
    status: str
    attempt_count: int
    scheduled_for: datetime | None
    started_at: datetime
    finished_at: datetime | None
    error: str | None
