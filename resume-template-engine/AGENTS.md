# Resume Template Engine

[Repository map](../AGENTS.md) | [Setup and rendering details](README.md)

## Purpose

This supporting Python package validates resume JSON with Pydantic, renders a
fixed Jinja2 HTML/CSS template, and exports selectable-text A4 PDFs through
Playwright/Chromium. It is a renderer, not a browser agent, job worker, or
general-purpose resume designer.

[Workers](../workers/AGENTS.md) consume it as an editable local dependency and
choose the resume content and artifact paths. The package also has a standalone
CLI, `resume-render`.

## Code map

- [resume_engine.py](resume_engine.py): resume models, rendering function, and CLI.
- [templates/resume.html](templates/resume.html) and
  [templates/resume.css](templates/resume.css): fixed document layout and styling.
- [examples](examples/): example JSON and career-source data; the career-source
  YAML is a facts bank, not the renderer's input schema.
- [audit_pdf.py](audit_pdf.py): structural/readability checks for generated PDFs.
- [stress_test.py](stress_test.py): pagination, bounds, content retention, Unicode,
  and invalid-input scenarios using temporary PDFs.
- [pyproject.toml](pyproject.toml): package dependencies and CLI entrypoint.

## Commands

Run from this directory with a usable Chromium installation or
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` configured:

```powershell
uv sync
uv run python resume_engine.py examples\resume.json --output output\resume.pdf --html output\resume.html
```

For rendering/layout changes, use the existing checks below. They additionally
require PyMuPDF (`fitz`), which is not a core renderer dependency:

```powershell
uv run --with pymupdf python stress_test.py
uv run --with pymupdf python audit_pdf.py output\resume.pdf examples\resume.json
```

## Change boundaries

- Preserve the schema and rendering interface used by workers, or update those
  call sites together. Keep JSON as the rendered content source.
- Do not invent candidate facts, modify the broader career facts bank while
  tailoring a resume, or copy private candidate details into documentation/tests.
- Preserve selectable text, clickable contact links, A4 dimensions, natural
  pagination, and education-block cohesion. One-page output is a content target,
  not a universal renderer constraint.
- Inspect generated output after content/template changes. The original fixture's
  page-specific audit expectations do not apply unchanged to every resume.
- Generated HTML/PDF files are artifacts, not template source. Structural checks
  are not a commercial ATS score or a guarantee of ranking.
