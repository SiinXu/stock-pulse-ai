# Bounded Image OCR Agent Tool

StockPulse can optionally extract **raw text** from local images and
PDF pages that embed rasters with Tesseract. Product targets cover
screenshots, filing/PDF page images, table-like statements, and chart
annotations via ``document_kind``. This phase is useful for low-cost text
recovery, but it does not claim verified table cells, OCR confidence,
brokerage-statement accuracy, or semantic chart understanding (use
``read_price_chart`` for K-line semantics). OCR text is never
decision-authoritative.

Optional secondary verification before high-impact conclusions and shared
agent-tool budget/rate-limit accounting remain open on issue #196.

## Choosing the right path

| Path | Image bytes | Result | Use it for |
| --- | --- | --- | --- |
| `extract_image_text` | Stays on host | Redacted, untrusted raw text + kind labels | Bounded text/number recovery from screenshots, filings, table statements, chart labels, and raster PDF pages |
| `read_price_chart` | Sent to configured Vision model | Semantic chart interpretation | K-line trend/levels |
| Image stock extract | Sent to configured Vision model | Stock codes/names | Symbol extraction |
| `parse_financial_pdf` | Stays on host | Existing text layer | Non-raster / text-layer PDFs |

OCR complements these owners; it does not reimplement them.

## Document kinds

Callers should set `document_kind` so the envelope and structural hints match
the intended target:

| `document_kind` | Input | Structural hints | Not claimed |
| --- | --- | --- | --- |
| `screenshot` (default) | PNG/JPEG/WebP/GIF | Raw text only | layout |
| `filing_page` | Image or raster PDF page | Raw text only; text-layer PDFs → `parse_financial_pdf` | full filing parse |
| `table_statement` | Table-like image | Unverified whitespace-split candidate rows (not brokerage-grade cells) | verified cells |
| `chart_annotation` | Chart screenshot | Sparse label tokens only; semantic charts stay on `read_price_chart` | chart semantics |
| `pdf_page` | PDF with embedded images | First embedded raster on `page_index`; fails closed when no embedded image | text-layer PDF parse / vector rasterization |

Every kind returns the same untrusted document envelope:
`trust.classification=untrusted_user_document`,
`trust.authoritative_for_decisions=false`, and
`instructions_authoritative=false`. After a successful OCR call, BoundToolSession
blocks follow-on tools until a new user turn.

## Privacy and trust boundary

“Local OCR” means **image bytes stay on the host**. The returned text becomes a
tool-result message and may reach the configured Agent model. StockPulse always
redacts the supported email, secret assignment, broker/account identifier,
labeled phone, and Chinese government-ID classes before returning text. Raw OCR
text is not logged or persisted by this service. Tool audit summaries for
`extract_image_text` store redacted metadata only (status, kind, hashes/counts),
not full statement body text.

Redaction is a bounded safeguard, not a proof that arbitrary personal data was
removed. Operators requiring zero remote egress must enable the canonical
`LOCAL_ONLY_MODE=true` gate and use a loopback model. Enabling the default-off
OCR tool is the current operator opt-in boundary; per-user consent and
multi-tenant data ownership are not implemented by this phase.

Every OCR string is attacker-controlled document data. The result labels it
`untrusted_user_document` / `untrusted_document_data`, sets
`authoritative_for_decisions=false`, and tells the runtime not to obey embedded
instructions or treat them as authorization. After a successful OCR call in a
`BoundToolSession`, follow-on tools in the same turn are fenced until a new
user reauthorization (same pattern as earnings-transcript parsing).

Tool capabilities remain governed by ToolSurface / BoundToolSession allowlist;
document text cannot grant a capability or bypass the session allowlist.

## Resource and file contract

- Path must resolve under `OCR_FILE_ROOT` (or `MULTIMODAL_FILE_ROOT`). Raster images and PDF pages with embedded images are accepted; text-layer PDFs should use `parse_financial_pdf`.
- The service opens the resolved path once, rejects non-regular files, reads at
  most 5 MiB + 1 byte, and verifies suffix plus image signature (or PDF header).
- PDF pages: extract one embedded raster via pypdf; no silent vector rasterization.
- Pillow inspects the header before RGB conversion. Width/height are at most
  10,000, decoded pixels at most 25,000,000, and only one frame is accepted.
  Decompression-bomb warnings/errors are failures.
- OCR runs in an isolated process group. The 1–120 second wall-clock deadline
  terminates and reaps the worker and POSIX descendants.
- The entire JSON tool result is at most 32 KiB UTF-8. Text is stored once,
  truncated on a valid UTF-8 boundary, and reports original counts and
  truncation state.
- Source provenance contains MIME, byte size, dimensions, frame count, SHA-256,
  language selection, engine, engine version, and document kind; it does not
  expose a local path or filename.
- Failures return `status=unavailable` (or `degraded` for empty OCR text) with
  an explicit `reason_code` — never a silent empty success.

## Registration and installation

The `builtin.ocr` plugin registers `extract_image_text` only after all gates:

1. `OCR_AGENT_TOOL_ENABLED=true`
2. `OCR_FILE_ROOT` or fallback `MULTIMODAL_FILE_ROOT`
3. optional Python packages from `requirements/ocr.txt`
4. system Tesseract binary and selected language packs

```bash
python -m pip install --constraint constraints.txt --build-constraint build-constraints.txt -r requirements/ocr.txt
# macOS: brew install tesseract tesseract-lang
# Debian: apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
```

```bash
OCR_AGENT_TOOL_ENABLED=false
# OCR_FILE_ROOT=/absolute/path/to/ocr-uploads
# OCR_LANGS=chi_sim+eng
# OCR_TIMEOUT_SECONDS=30
```

Restart after changing registration settings. The default Docker/Desktop
packages do not install the system Tesseract binary or language data; treat
those surfaces as unsupported until operators add and verify them explicitly.
The synthetic EN/ZH and multi-kind fixtures validate the safety envelope with
injected engine output. A real English Tesseract check remains optional when
the host provides the binary; this phase does not claim required
Chinese/dense-table quality.

PR CI (`ocr-stock-extractor`) installs `requirements/ocr.txt` plus `tesseract-ocr`
and `tesseract-ocr-eng` when extractor paths change, then runs the existing
offline extractor tests and treats dependency skips as failures. It does not
install `chi_sim` or make network tests blocking.

## Rollback

Set `OCR_AGENT_TOOL_ENABLED=false` and restart, or revert the PR. No database
migration or cleanup is required.
