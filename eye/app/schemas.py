from datetime import datetime, time
from enum import StrEnum
from typing import Annotated, Any, Literal

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
    task_id: str
    agent_id: str
    agent_name: str
    status: str


class SubAgentCallback(BaseModel):
    job_id: str
    callback_token: str
    status: Annotated[str, Field(pattern="^(completed|failed)$")]
    response: dict[str, Any] | None = None
    error: Annotated[str | None, Field(max_length=4_000)] = None


class SubAgentNotification(BaseModel):
    job_id: str
    agent_id: str
    agent_name: str
    status: str
    payload: dict[str, Any]
    response: dict[str, Any] | None
    error: str | None
    created_at: datetime
    completed_at: datetime


class WorkflowRunNotification(BaseModel):
    kind: Literal["workflow_run"] = "workflow_run"
    run_id: str
    workflow_id: str
    workflow_name: str
    attempt_count: int
    status: Literal["succeeded", "failed"]
    error: str | None
    created_at: datetime
    completed_at: datetime


class WorkflowStepType(StrEnum):
    SUB_AGENT = "sub_agent"
    COMMAND = "command"


class WorkflowStepCreate(BaseModel):
    step_type: WorkflowStepType = WorkflowStepType.SUB_AGENT
    sub_agent_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    command: Annotated[str | None, Field(min_length=1, max_length=20_000)] = None
    working_directory: Annotated[str | None, Field(min_length=1, max_length=2048)] = None
    timeout_seconds: Annotated[int, Field(ge=1, le=86_400)] = 300

    @model_validator(mode="after")
    def validate_step_type(self) -> "WorkflowStepCreate":
        if self.step_type == WorkflowStepType.COMMAND:
            if self.command is None or not self.command.strip() or "\u0000" in self.command:
                raise ValueError("A non-empty command is required for a command step")
            if self.sub_agent_id is not None:
                raise ValueError("Command steps must have sub_agent_id=null")
            if self.payload:
                raise ValueError("Command steps do not accept a sub-agent payload")
        else:
            if not self.sub_agent_id:
                raise ValueError("sub_agent_id is required for a sub-agent step")
            if self.command is not None or self.working_directory is not None:
                raise ValueError("Command fields are only valid for command steps")
        if self.working_directory is not None and "\u0000" in self.working_directory:
            raise ValueError("working_directory cannot contain null characters")
        return self


class WorkflowStepResponse(BaseModel):
    id: str
    position: int
    step_type: WorkflowStepType
    sub_agent_id: str | None
    payload: dict[str, Any]
    command: str | None
    working_directory: str | None
    timeout_seconds: int


class WorkflowCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str, Field(max_length=4_000)] = ""
    steps: Annotated[list[WorkflowStepCreate], Field(min_length=1)]
    enabled: bool = True


class WorkflowUpdate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    description: Annotated[str, Field(max_length=4_000)] | None = None
    steps: Annotated[list[WorkflowStepCreate], Field(min_length=1)] | None = None
    enabled: bool | None = None


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


class WorkerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    enabled: bool
    created_at: datetime
    modified_at: datetime


class WorkerTaskRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    worker_id: str
    celery_task_id: str
    job_url: str
    company_name: str = "NA"
    job_title: str = "NA"
    package: str = "NA"
    platform: str = "NA"
    payload: dict[str, Any]
    result: dict[str, Any] | None
    status: str
    started: bool
    success: bool
    failed: bool
    step_failed: str | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class WorkerMetricsResponse(BaseModel):
    total_runs: int
    running: int
    succeeded: int
    failed: int
    skipped: int
    success_rate: float | None


class WorkerSkipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_run_id: str
    job_url: str
    reason: str
    details: str
    created_at: datetime


class WorkerDashboardResponse(BaseModel):
    worker: WorkerResponse
    metrics: WorkerMetricsResponse
    runs: list[WorkerTaskRunResponse]
    total: int
    page: int
    page_size: int


class WorkerLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    worker_id: str
    task_run_id: str
    level: str
    step: str
    message: str
    details: dict[str, Any] | None
    created_at: datetime
