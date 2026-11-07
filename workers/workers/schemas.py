from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Contact(StrictModel):
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    location: str = ""


class SkillGroup(StrictModel):
    label: str
    items: list[str]


class Experience(StrictModel):
    role: str
    company: str
    dates: str = ""
    location: str = ""
    client_or_project: str | None = None
    bullets: list[str] = Field(default_factory=list)


class Project(StrictModel):
    name: str
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)


class EducationItem(StrictModel):
    qualification: str
    dates: str = ""
    institution: str = ""


class Resume(StrictModel):
    name: str
    headline: str = ""
    contact: Contact = Field(default_factory=Contact)
    summary: str = ""
    skills: list[SkillGroup] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)


class ResumeTailoringResult(StrictModel):
    is_redflag: bool
    update_required: bool
    reason: str = Field(min_length=1)
    resume: Resume | None

    @model_validator(mode="after")
    def validate_decision(self) -> "ResumeTailoringResult":
        if self.is_redflag:
            if self.update_required or self.resume is not None:
                raise ValueError("A red-flag job must not tailor or return a resume")
        elif self.resume is None:
            raise ValueError("An eligible job must return a complete resume (original if no update is needed)")
        return self


class JobApplicationResult(StrictModel):
    task_run_id: str
    status: Literal["succeeded", "skipped"]
    resume_updated: bool = False
    resume_id: str | None = None
    resume_path: str | None = None
    browser_session_id: str | None = None
    browser_result: dict | None = None
    skip_reason: Literal["duplicate", "redflag"] | None = None
    reason: str | None = None
