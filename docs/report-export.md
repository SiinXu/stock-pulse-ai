# Report Export (Markdown / PDF)

StockPulse can export the already-rendered Markdown for one history record. It
does not rerun analysis or modify persisted history. Markdown is the lossless
archive; PDF is an optional, bounded presentation transform.

Chinese: [report-export_CN.md](report-export_CN.md)

## Formats in this release

| Format | Availability | Contract |
| --- | --- | --- |
| Markdown (`.md`) | Always | Exact UTF-8 content from the existing history Markdown surface |
| PDF (`.pdf`) | Optional | Requires validated fpdf2 + a single-face TTF/OTF covering every visible report glyph |
| DOCX / XLSX | Not implemented | Remaining Issue #163 scope |

PDF remains unavailable when the dependency, font parser, representative
language glyphs, or deterministic font/backend smoke is not ready. Markdown is
unaffected by every PDF readiness state.

## Optional dependency choice

fpdf2 is pure Python and does not add Cairo/Pango or a headless browser to the
default StockPulse install. Its manual layout cost is owned by the exporter:
measured cell wrapping, page-aware rows, repeated table headers, and page limits
are tested directly.

Install the exact optional set after the base application:

```bash
python -m pip install --build-constraint build-constraints.txt \
  -r requirements-report-export.txt
```

The optional file pins `fpdf2==2.8.3`, `fonttools==4.63.0`, and
`markdown-it-py==4.2.0`, and also applies the repository's `constraints.txt`.
A legacy PyFPDF distribution sharing the `fpdf` import namespace is rejected
rather than treated as fpdf2. All three imports remain lazy, so a default
installation can start and use lossless Markdown export without the PDF set.

## Font readiness

`REPORT_EXPORT_PDF_FONT_PATH` is owned by the shared Config loader and system
configuration registry. It may point to one `.ttf` or `.otf` face. An explicit
invalid path fails closed and never silently falls back to a different system
font. When the field is empty, a small documented set of single-face system
font paths is probed. `.ttc` collection indices are not guessed.

Readiness has two layers:

1. The capability endpoint parses the font, checks representative glyphs for
   the requested language, and runs a small fpdf2 render smoke.
2. Every PDF request checks the exact visible codepoints produced from that
   report. If even one glyph is missing, the request returns
   `export_font_coverage_missing` instead of dropping icons or producing tofu.

This distinction matters for fonts such as Arial Unicode: they may cover CJK
text but not common report symbols such as `✅`, `⚠`, `🚨`, or `📊`.

Example:

```bash
export REPORT_EXPORT_PDF_FONT_PATH=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf
```

Absolute font paths and raw font-parser errors are logged only in sanitized
operator diagnostics. They are never returned by the capability or error API.

## Markdown-to-PDF transformations

The exporter uses `markdown-it-py` tokens rather than regular expressions.
Visible text is preserved, while these presentation transformations are
intentional:

- headings, paragraphs, block quotes, fenced code, ordered/unordered nested
  lists, and tables are rendered as PDF layout primitives;
- emphasis markers and inline-code markers are removed but their visible text
  remains;
- link labels remain, while link destinations are omitted;
- the complete image destination and title are discarded, the image is never
  fetched, and the visible alt text plus an omission note remains;
- tables with up to six columns use measured, wrapped grid cells; headers repeat
  after page breaks and normal rows move together to the next page;
- a single row taller than a page is split without deleting text;
- seven-to-twelve-column tables use a complete stacked header/value layout;
- Markdown is always available when callers need the exact source syntax,
  destinations, or an image-aware downstream archive.

The parser discards nested-parenthesis and signed image URLs as a whole, so no
query-string fragment can remain in the PDF.

## Bounded execution

PDF conversion is synchronous but has an explicit owner and degradation
contract:

| Bound | Default | Failure |
| --- | ---: | --- |
| UTF-8 input | 1,000,000 bytes | 413 `export_input_too_large` |
| Pages | 100 | 413 `export_page_limit_exceeded` |
| Rows per table | 500 | 413 `export_table_rows_exceeded` |
| Columns per table | 12 | 413 `export_table_columns_exceeded` |
| Total table cells | 3,000 | 413 `export_table_cells_exceeded` |
| Monotonic render deadline | 20 seconds | 503 `export_deadline_exceeded` |
| Concurrent renders per process | 2 | 429 `export_busy` |

Successful PDFs use a bounded process-local LRU cache (12 entries, 24 MiB). The
cache key includes Markdown content, title, and font file signature; PDF bytes
are never persisted by the exporter.

## API

### Capabilities

```http
GET /api/v1/history/export/capabilities?language=zh
```

`language` is one of `en`, `zh`, `zh-TW`, `ja`, or `ko`. The typed response
contains fixed `md` and `pdf` capabilities, sanitized readiness status, optional
dependency version, glyph count, and all public limits. It never includes a
font path.

### Export

```http
GET /api/v1/history/{record_id}/export?format=md
GET /api/v1/history/{record_id}/export?format=pdf
```

`format` is the OpenAPI enum `md | pdf`. The 200 response declares both
`text/markdown` and `application/pdf` binary bodies. Downloads send a short
ASCII `filename=` fallback plus bounded RFC 5987 `filename*=UTF-8''...`, so
Unicode history identities do not fail Starlette header encoding.

| Status | Representative code | Meaning |
| --- | --- | --- |
| 400 | `export_format_invalid` | Unsupported direct-call format |
| 404 | `not_found` | History record is absent |
| 413 | `export_*_exceeded` | Deterministic size/table/page bound |
| 429 | `export_busy` | All per-process render slots are occupied |
| 500 | `generation_failed` | History Markdown generation failed |
| 503 | `export_dependency_missing` | fpdf2 missing, incompatible, or legacy namespace conflict |
| 503 | `export_font_*` | Font invalid, unavailable, or missing exact report glyphs |
| 503 | `export_deadline_exceeded` | Monotonic render deadline exceeded |

## Remaining Issue #163 scope

- DOCX structured export
- XLSX score/metric sheets
- optional evidence/audit appendix toggle (#127)
- Web one-click export controls on report and DecisionSignal surfaces

This PR is backend-only; it does not change templates, report generation,
Desktop, `pdf_parsing_service.py`, share-image, or `md2img`.
