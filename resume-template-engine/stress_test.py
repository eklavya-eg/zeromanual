from __future__ import annotations

import copy
import json
import re
import tempfile
from pathlib import Path

import fitz
from pydantic import ValidationError

from resume_engine import Resume, render

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "examples" / "resume.json"


def normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def expected_content(data: dict) -> list[str]:
    values = [data.get("name", ""), data.get("headline", ""), data.get("summary", "")]
    values.extend(v for v in data.get("contact", {}).values() if v)
    for group in data.get("skills", []):
        values.extend([group["label"], *group["items"]])
    for job in data.get("experience", []):
        values.extend([job["role"], job["company"], job.get("dates", ""), job.get("location", ""), job.get("client_or_project", ""), *job.get("bullets", [])])
    for project in data.get("projects", []):
        values.extend([project["name"], project.get("dates", ""), *project.get("bullets", [])])
    for item in data.get("education", []):
        values.extend([item["qualification"], item.get("dates", ""), item.get("institution", "")])
    return [v for v in values if v]


def make_scenarios(base: dict) -> dict[str, dict]:
    scenarios = {"baseline": copy.deepcopy(base), "minimal": {"name": "Test Candidate"}}

    repeated = " ".join(["Designed and implemented scalable backend services using Python, FastAPI, PostgreSQL, Redis, Docker and distributed systems architecture, improving reliability and performance across production workloads."] * 4)
    heavy = copy.deepcopy(base)
    heavy["summary"] = " ".join(["Experienced product engineer building reliable software systems and AI-powered applications."] * 5)
    heavy["skills"] = [{"label": f"Skill Category {i}", "items": [f"Technology {i}-{j}" for j in range(1, 19)]} for i in range(1, 9)]
    heavy["experience"] = [
        {"role": f"Senior Backend Engineer {i}", "company": f"Example Technology Company {i}", "dates": "Jan 2020 - Present", "location": "Remote / India", "client_or_project": f"Large Scale Project {i}", "bullets": [f"{repeated} Detail marker JOB{i}-BULLET{j}." for j in range(1, 5)]}
        for i in range(1, 16)
    ]
    heavy["projects"] = [{"name": f"Project {i}", "dates": "2020 - 2024", "bullets": [f"{repeated} PROJECT{i}-BULLET{j}." for j in range(1, 4)]} for i in range(1, 9)]
    heavy["education"] = [{"qualification": f"Degree {i}", "dates": "2018 - 2022", "institution": f"University {i}"} for i in range(1, 7)]
    scenarios["heavy_many_entries"] = heavy

    oversized = copy.deepcopy(base)
    oversized["experience"] = [{"role": "Long Single Role", "company": "Stress Test Corp", "dates": "2020 - Present", "location": "Remote", "bullets": [f"LONGENTRY-{i} {repeated}" for i in range(1, 75)]}]
    oversized["projects"] = []
    oversized["education"] = []
    scenarios["single_oversized_entry"] = oversized

    unicode_case = copy.deepcopy(base)
    unicode_case["name"] = "Zoë Li Candidate"
    unicode_case["summary"] = "Résumé & systems engineering with 100% focus on reliability; C++ / C# / Node.js."
    unicode_case["experience"][0]["bullets"].append("Unicode test: naïve café — 東京 — مرحبا — & angle brackets <candidate>.")
    scenarios["unicode_content"] = unicode_case

    long_token = copy.deepcopy(base)
    long_token["experience"][0]["bullets"].append("UNBROKEN-" + "X" * 400)
    scenarios["long_unbroken_token"] = long_token
    return scenarios


def check_pdf(name: str, data: dict, pdf_path: Path) -> dict:
    doc = fitz.open(pdf_path)
    pages_text = [page.get_text(sort=True) for page in doc]
    combined = normalize(" ".join(pages_text))
    expected = expected_content(data)
    missing = [value for value in expected if normalize(value) not in combined]
    bounds_errors = []
    page_top_y = []
    for page_number, page in enumerate(doc, start=1):
        if abs(page.rect.width - 595.276) > 1 or abs(page.rect.height - 841.89) > 1:
            bounds_errors.append(f"Page {page_number} is not A4")
        blocks = [block for block in page.get_text("blocks") if len(block) > 4 and str(block[4]).strip()]
        page_top_y.append(round(min((block[1] for block in blocks), default=0), 1))
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    x0, y0, x1, y1 = span["bbox"]
                    if x0 < -0.5 or y0 < -0.5 or x1 > page.rect.width + 0.5 or y1 > page.rect.height + 0.5:
                        bounds_errors.append(f"Page {page_number} text outside page: {span['text'][:30]}")
    no_text_pages = [i + 1 for i, text in enumerate(pages_text) if len(text.strip()) < 10]
    return {
        "scenario": name,
        "pages": len(doc),
        "expected_fields_and_entries": len(expected),
        "missing_content": len(missing),
        "missing_examples": missing[:2],
        "a4_and_bounds_errors": bounds_errors,
        "blank_or_nontext_pages": no_text_pages,
        "top_text_y_points": page_top_y,
        "selectable_text": all(len(text.strip()) > 10 for text in pages_text),
        "pdf_bytes": pdf_path.stat().st_size,
    }


def main() -> int:
    base = json.loads(SOURCE.read_text(encoding="utf-8"))
    scenarios = make_scenarios(base)
    results = []
    with tempfile.TemporaryDirectory(prefix="resume-engine-stress-") as temp_dir:
        temp = Path(temp_dir)
        for name, data in scenarios.items():
            json_path = temp / f"{name}.json"
            pdf_path = temp / f"{name}.pdf"
            json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            Resume.model_validate(data)
            render(json_path, pdf_path)
            results.append(check_pdf(name, data, pdf_path))

    invalid_rejected = False
    try:
        Resume.model_validate({"name": "Invalid", "experience": [{"company": "Missing role"}]})
    except ValidationError:
        invalid_rejected = True

    print(json.dumps({"results": results, "invalid_schema_rejected": invalid_rejected}, indent=2, ensure_ascii=False))
    failed = any(r["missing_content"] or r["a4_and_bounds_errors"] or r["blank_or_nontext_pages"] or not r["selectable_text"] for r in results)
    return 1 if failed or not invalid_rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
