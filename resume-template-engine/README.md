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

## Current one-page application resume

- [Career source](examples/career-source.yaml): concise facts bank containing experience, projects, categorized skills, education, and achievements, plus basic contact details. Skills use inline comma-separated YAML lists.
- [Application JSON](examples/updated%20resume.json): the selected one-page Backend / AI Engineer resume in the existing renderer schema.
- Generated files: `output/Eklavya_Gupta_Backend_AI_Resume.pdf` and `output/Eklavya_Gupta_Backend_AI_Resume.html`.

For each job description, select relevant facts from the career source and tailor the application JSON; do not copy the whole YAML into the resume. The YAML is not the renderer schema and no longer embeds a resume or export mapping. Keep the broader facts bank intact when tailoring, preserve employment dates and reported metrics, and add achievements only when supplied.

The source retains both Infigos phases: full-time Jun-Nov 2025 for RFP automation and internship Dec 2024-May 2025 for banking, ML, and Figma work. The application JSON remains a separate, selective one-page document. The original `examples/resume.json` is a historical input; the template is unchanged.

After tailoring the JSON, regenerate the PDF from this directory:

```powershell
python resume_engine.py "examples\updated resume.json" --output "output\Eklavya_Gupta_Backend_AI_Resume.pdf" --html "output\Eklavya_Gupta_Backend_AI_Resume.html"
```

If Playwright's downloaded Chromium is unavailable, the renderer can use an installed Chrome or Edge executable, for example:

```powershell
$env:PLAYWRIGHT_CHROMIUM_EXECUTABLE = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
```

Recheck pagination after content edits; one page is a content target, not a renderer constraint. The bundled audit below expects education on page 2 for the original fixture, so that particular check is not applicable to this one-page variant. Check its selectable text, contact links, text bounds, content retention, and one-page count instead. Keep salary/notice-period preferences out of application exports and confirm permission to disclose client names and internal metrics before sharing externally.

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
