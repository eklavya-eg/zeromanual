from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import fitz


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def expected_strings(data: dict) -> list[str]:
    values = [data.get("name", ""), data.get("summary", "")]
    contact = data.get("contact", {})
    values.extend(v for v in contact.values() if v)
    for group in data.get("skills", []):
        values.append(group["label"])
        values.extend(group["items"])
    for job in data.get("experience", []):
        values.extend([job["role"], job["company"], job.get("dates", ""), job.get("location", ""), job.get("client_or_project", "")])
        values.extend(job.get("bullets", []))
    for project in data.get("projects", []):
        values.extend([project["name"], project.get("dates", "")])
        values.extend(project.get("bullets", []))
    for item in data.get("education", []):
        values.extend([item["qualification"], item.get("dates", ""), item.get("institution", "")])
    return [v for v in values if v]


def audit(pdf_path: Path, json_path: Path) -> int:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    doc = fitz.open(pdf_path)
    text_by_page = [page.get_text(sort=True) for page in doc]
    all_text = "\n".join(text_by_page)
    normalized_pdf = norm(all_text)
    failures = []
    checks = []

    checks.append(("A4 page dimensions", all(abs(p.rect.width - 595) < 1 and abs(p.rect.height - 842) < 1 for p in doc)))
    checks.append(("Selectable text on every page", all(len(t.strip()) > 20 for t in text_by_page)))
    checks.append(("Expected section headings", all(h in all_text.upper() for h in ["SKILLS", "WORK EXPERIENCE", "PROJECTS", "EDUCATION"])))
    checks.append(("Contact details extractable", all(norm(v) in normalized_pdf for v in data.get("contact", {}).values() if v)))

    missing = []
    for value in expected_strings(data):
        tokens = norm(value)
        if len(tokens) >= 8 and tokens not in normalized_pdf:
            missing.append(value[:90])
    checks.append((f"Resume content present ({len(expected_strings(data)) - len(missing)}/{len(expected_strings(data))} fields/entries)" , not missing))

    page1 = text_by_page[0].upper() if text_by_page else ""
    page2 = text_by_page[1].upper() if len(text_by_page) > 1 else ""
    checks.append(("Projects remain on page 1", "PROJECTS" in page1))
    checks.append(("Education starts on page 2", "EDUCATION" in page2 and "EDUCATION" not in page1))

    out_of_bounds = []
    for page_no, page in enumerate(doc, start=1):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    x0, y0, x1, y1 = span["bbox"]
                    if x0 < -0.5 or y0 < -0.5 or x1 > page.rect.width + 0.5 or y1 > page.rect.height + 0.5:
                        out_of_bounds.append((page_no, span["text"][:40]))
    checks.append(("No text outside page boundaries", not out_of_bounds))

    links = sum(len(p.get_links()) for p in doc)
    checks.append((f"Clickable contact links ({links} detected)", links >= 4))

    for label, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            failures.append(label)
    if missing:
        print("Missing/altered text samples:")
        for item in missing[:10]:
            print(f"  - {item}")
    if out_of_bounds:
        print("Out-of-bounds text:", out_of_bounds[:5])
    print(f"\nPages: {len(doc)} | Extracted characters: {len(all_text)} | Embedded images: {sum(len(p.get_images()) for p in doc)}")
    print("Note: this is a structural ATS-readability audit, not a score from a commercial ATS.")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("json", type=Path)
    args = parser.parse_args()
    raise SystemExit(audit(args.pdf, args.json))
