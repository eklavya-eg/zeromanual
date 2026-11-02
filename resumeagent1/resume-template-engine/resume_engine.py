from __future__ import annotations
import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field, HttpUrl, ValidationError
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent

class Contact(BaseModel):
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    location: str = ""

class SkillGroup(BaseModel):
    label: str
    items: list[str]

class Experience(BaseModel):
    role: str
    company: str
    dates: str = ""
    location: str = ""
    client_or_project: Optional[str] = None
    bullets: list[str] = Field(default_factory=list)

class Project(BaseModel):
    name: str
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)

class EducationItem(BaseModel):
    qualification: str
    dates: str = ""
    institution: str = ""

class Resume(BaseModel):
    name: str
    headline: str = ""
    contact: Contact = Field(default_factory=Contact)
    summary: str = ""
    skills: list[SkillGroup] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)


def render(data_path: Path, output_path: Path, html_path: Path | None = None) -> None:
    raw = json.loads(data_path.read_text(encoding="utf-8"))
    resume = Resume.model_validate(raw)
    env = Environment(
        loader=FileSystemLoader(BASE_DIR / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    css = (BASE_DIR / "templates" / "resume.css").read_text(encoding="utf-8")
    html = env.get_template("resume.html").render(resume=resume, css=css)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if html_path:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        executable = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or shutil.which("chromium") or shutil.which("chromium-browser")
        launch_options = {"headless": True}
        if executable:
            launch_options["executable_path"] = executable
        if os.name != "nt":
            launch_options["args"] = ["--no-sandbox"]
        browser = p.chromium.launch(**launch_options)
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        page.pdf(
            path=str(output_path),
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
            display_header_footer=False,
        )
        browser.close()
    print(f"PDF created: {output_path}")
    if html_path:
        print(f"HTML preview: {html_path}")


def main():
    parser = argparse.ArgumentParser(description="Render resume JSON into the fixed A4 resume template")
    parser.add_argument("input", type=Path, help="Path to resume JSON")
    parser.add_argument("--output", type=Path, default=Path("output/resume.pdf"))
    parser.add_argument("--html", type=Path, default=Path("output/resume.html"), help="Also save rendered HTML")
    args = parser.parse_args()
    try:
        render(args.input, args.output, args.html)
    except ValidationError as exc:
        print("Resume JSON validation failed:")
        print(exc)
        raise SystemExit(2)

if __name__ == "__main__":
    main()
