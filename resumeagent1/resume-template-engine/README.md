# Resume Template Engine

A template-specific JSON → HTML/CSS → PDF renderer based on the uploaded two-page A4 resume.

## What it does

- Accepts a validated JSON structure using Pydantic.
- Renders a fixed resume design using Jinja2 + semantic HTML/CSS.
- Uses Chromium via Playwright to export selectable-text A4 PDFs.
- Uses natural document flow for dynamic pagination.
- Keeps the education section together so it starts on a fresh page when it cannot fit as a whole.
- Adds clickable email, phone, LinkedIn, GitHub and website links.
- Saves intermediate HTML for inspection.

## Setup

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Generate PDF

```bash
python resume_engine.py examples/resume.json --output output/resume.pdf --html output/resume.html
```

## Run structural / ATS-readability audit

```bash
pip install pymupdf
python audit_pdf.py output/resume.pdf examples/resume.json
```

The audit checks A4 dimensions, selectable text, section headings, presence of the JSON content, page placement, text outside page boundaries, and clickable contact links. It is a structural readability check, **not a commercial ATS score or a guarantee of ranking**.

## JSON format

See `examples/resume.json`. Supported fields:

- `name`, `headline`, `contact`, `summary`
- `skills`: list of `{ "label": str, "items": [str] }`
- `experience`: list of `{ "role", "company", "dates", "location", "client_or_project", "bullets" }`
- `projects`: list of `{ "name", "dates", "bullets" }`
- `education`: list of `{ "qualification", "dates", "institution" }`

## Template customization

Edit `templates/resume.html` and `templates/resume.css`. JSON remains the content source. The renderer uses semantic headings, paragraphs, lists and links to keep text extractable by document parsers.

## Pagination

Chromium's print layout handles pagination naturally. Content can flow to additional A4 pages. Individual experience/project entries are kept together when possible; very long entries may split when required. The education section is kept together to avoid an orphaned heading or a split education block.

## Limitations

- This creates a new PDF; it does not modify the original PDF's internal objects. The uploaded original remains untouched.
- Font metrics and line wrapping can differ slightly from the original PDF.
- This template is intentionally fixed; it is not a general-purpose resume designer.

## Stress tests

Run the included stress suite with:

```bash
python stress_test.py
```

It generates temporary PDFs for baseline, minimal, high-volume, oversized-entry, Unicode, and long-unbroken-token cases. It checks expected content retention, A4 page dimensions, text bounds, selectable text, and invalid JSON rejection. Temporary test PDFs are removed automatically.
