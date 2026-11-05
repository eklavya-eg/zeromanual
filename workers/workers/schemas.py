from pydantic import BaseModel, ConfigDict, Field


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
    update_required: bool
    reason: str
    resume: Resume | None


class JobApplicationResult(StrictModel):
    task_run_id: str
    status: str
    resume_updated: bool
    resume_id: str
    resume_path: str
    browser_session_id: str
    browser_result: dict
