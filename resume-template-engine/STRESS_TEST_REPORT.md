# Resume Engine Stress Test Report

**Result: PASS — 6 rendering scenarios and schema rejection test.**

| Scenario | Pages | Expected fields/entries retained | A4 / bounds | Selectable text |
|---|---:|---:|---|---|
| Existing resume (baseline) | 2 | 92 / 92 | Pass | Pass |
| Minimal resume | 1 | 1 / 1 | Pass | Pass |
| High-volume resume (15 jobs, 8 projects, 6 education entries, 8 skill groups) | 11 | 352 / 352 | Pass | Pass |
| One oversized experience entry (74 long bullets) | 8 | 127 / 127 | Pass | Pass |
| Unicode content | 2 | 93 / 93 | Pass | Pass |
| 400-character unbroken token | 2 | 93 / 93 | Pass | Pass |

Additional checks:

- No blank or non-text pages were produced.
- No extracted text span exceeded page bounds.
- Every generated page had A4 dimensions.
- Repeated page top offsets were consistent (approximately 22 pt on continuation pages), preserving the pagination margin.
- Invalid resume data was rejected by Pydantic.
- The normal two-page resume passed `audit_pdf.py`: 92/92 expected content items, all section checks, A4, selectable text, no out-of-bounds text, and five clickable contact links.

## Fix made during testing

The long unbroken-token test initially exposed clipped text. Added `overflow-wrap: anywhere` and `word-wrap: break-word` to the resume container. Re-running the test confirmed the full token is retained and the document flows to an additional page.

## Scope and limitations

This verifies rendering, text retention, page geometry and basic extractability for the test cases. It is not a guarantee of compatibility with every ATS, PDF viewer, font environment or arbitrarily malformed input. Very large individual entries can span multiple pages; they are not forcibly kept together when they exceed a page.
