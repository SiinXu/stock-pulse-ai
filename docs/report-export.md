# Report Export (PDF / Markdown)

StockPulse can export a **already-rendered** analysis report to archive-friendly
formats. Export is a presentation-layer conversion: it does not change report
structure or wording, and it does not re-run analysis.

## Formats in this release

| Format | Availability | Notes |
| --- | --- | --- |
| Markdown (`.md`) | Always | Same content as `GET /api/v1/history/{id}/markdown` |
| PDF (`.pdf`) | Optional | Requires `fpdf2` + a CJK/Unicode `.ttf`/`.otf` font |
| DOCX / XLSX | Not implemented | Remaining scope for Issue #163 |

## Why fpdf2 (not WeasyPrint / browser)

| Option | Pros | Cons for StockPulse |
| --- | --- | --- |
| **fpdf2 (chosen)** | Pure Python; no system libraries; small optional install | Manual Markdown layout; needs explicit font file for Chinese |
| WeasyPrint | Excellent HTML/CSS | Needs Cairo/Pango system packages — raises default install cost |
| Headless Chromium | Pixel-perfect HTML | Large download; fragile in CI/desktop packaging |

Default installs must stay unaffected: PDF code is imported only when exporting
to PDF, and missing optional deps return **HTTP 503** with an install hint.

## Install optional PDF dependency

```bash
# After the normal StockPulse requirements install:
python -m pip install --build-constraint build-constraints.txt -r requirements-report-export.txt
```

`requirements.txt` does **not** include fpdf2. Uninstalling the optional package
removes PDF export only.

## Chinese fonts

PDF export embeds a TrueType/OpenType font. Resolution order:

1. Environment variable `REPORT_EXPORT_PDF_FONT_PATH` (absolute path to `.ttf` or `.otf`)
2. Common OS locations (for example macOS `Arial Unicode.ttf`, Linux Noto/WenQuanYi TTF paths, Windows `msyh.ttf`)

**`.ttc` collection fonts are not used** without extra tooling. If no usable
font is found, the API returns `export_font_missing` (503) instead of producing
a PDF full of tofu boxes.

Example:

```bash
export REPORT_EXPORT_PDF_FONT_PATH=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
# Chinese reports need a CJK-capable face, e.g.:
# export REPORT_EXPORT_PDF_FONT_PATH=/path/to/NotoSansSC-Regular.otf
```

## Charts / images

Markdown image syntax (`![alt](url)`) is **omitted** in PDF and replaced with a
short note. Remote chart bytes are never fetched at export time (no network,
no secret leakage into the archive). Use the Markdown attachment when images
must be preserved for offline tools.

## API

### Capabilities

```http
GET /api/v1/history/export/capabilities
```

Returns which formats are available in the current process (without leaking
host font paths).

### Export a history record

```http
GET /api/v1/history/{record_id}/export?format=md
GET /api/v1/history/{record_id}/export?format=pdf
```

Success responses are file downloads (`Content-Disposition: attachment`).

| Status | Error code | Meaning |
| --- | --- | --- |
| 400 | `export_format_invalid` | Unknown format (e.g. docx before implementation) |
| 404 | `not_found` | No history record |
| 500 | `generation_failed` | Markdown rebuild failed |
| 503 | `export_dependency_missing` | fpdf2 not installed |
| 503 | `export_font_missing` | No usable font for PDF |

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `REPORT_EXPORT_PDF_FONT_PATH` | empty | Absolute path to a `.ttf`/`.otf` font for PDF text |

No configuration is required for Markdown export.

## Remaining scope (Issue #163)

- DOCX structured export
- XLSX tabular export (scores / metrics sheets)
- Optional evidence/audit appendix toggle (#127)
- Web one-click export buttons on report / DecisionSignal views

## Integration point

Backend-only in this change. Web can call:

```ts
// After merge: download helper against history export
// GET /api/v1/history/${recordId}/export?format=pdf
```

No Web UI wiring in this PR.
