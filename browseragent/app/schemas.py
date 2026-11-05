from typing import Annotated
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field, HttpUrl

from app.llm import LlmProvider


class SwitchCallback(BaseModel):
    job_id: str
    webhook_url: HttpUrl
    callback_token: str


class InvokePayload(BaseModel):
    task: Annotated[str, Field(min_length=1, max_length=20_000)]
    max_steps: Annotated[int, Field(ge=1, le=500)] = 100
    provider: LlmProvider | None = None
    model: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    id: UUID | None = None
    available_file_paths: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    switch_callback: SwitchCallback | None = Field(
        default=None,
        validation_alias=AliasChoices("_eye", "_switch"),
    )

    @property
    def eye_callback(self) -> SwitchCallback | None:
        return self.switch_callback


class InvokeAcceptedResponse(BaseModel):
    task_id: str
    status: str = "accepted"
    id: UUID | None = None
    instruction_id: UUID | None = None


class InvokeResponse(BaseModel):
    status: str
    result: str | None
    steps: int
    errors: list[str | None]
    provider: LlmProvider
    model: str
    id: UUID | None = None
