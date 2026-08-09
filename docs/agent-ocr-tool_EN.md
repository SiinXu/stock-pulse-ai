# Bounded Image OCR Agent Tool

StockPulse can optionally extract **raw text** from a local image with
Tesseract. This phase is useful for low-cost text recovery, but it does not
claim verified table cells, OCR confidence, brokerage-statement accuracy, or
semantic chart understanding. Those broader Issue #196 deliverables remain
open. Issue #218 is reference-only; OCR by itself is not an offline mode.

## Choosing the right path

| Path | Image bytes | Result | Use it for |
| --- | --- | --- | --- |
| `extract_image_text` | Stays on host | Redacted, untrusted raw text | Bounded text/number recovery |
| `read_price_chart` | Sent to configured Vision model | Semantic chart interpretation | K-line trend/levels |
| Image stock extract | Sent to configured Vision model | Stock codes/names | Symbol extraction |
| PDF parser | Stays on host | Existing text layer | Non-raster PDFs |

OCR complements these owners; it does not reimplement them.

## Privacy and trust boundary

“Local OCR” means **image bytes stay on the host**. The returned text becomes a
tool-result message and may reach the configured Agent model. StockPulse always
redacts the supported email, secret assignment, broker/account identifier,
labeled phone, and Chinese government-ID classes before returning text. Raw OCR
text is not logged or persisted by this service.

Redaction is a bounded safeguard, not a proof that arbitrary personal data was
removed. Operators requiring zero remote egress must enable the canonical
`LOCAL_ONLY_MODE=true` gate and use a loopback model. Enabling the default-off
OCR tool is the current operator opt-in boundary; per-user consent and
multi-tenant data ownership are not implemented by this phase.

Every OCR string is attacker-controlled document data. The result labels it
`untrusted_document_data` and tells the runtime not to obey embedded
instructions or treat them as authorization. Tool capabilities remain governed
by ToolSurface; document text cannot grant a capability.

## Resource and file contract

- Path must resolve under `OCR_FILE_ROOT` (or `MULTIMODAL_FILE_ROOT`).
- The service opens the resolved path once, rejects non-regular files, reads at
  most 5 MiB + 1 byte, and verifies suffix plus image signature.
- Pillow inspects the header before RGB conversion. Width/height are at most
  10,000, decoded pixels at most 25,000,000, and only one frame is accepted.
  Decompression-bomb warnings/errors are failures.
- OCR runs in an isolated process group. The 1–120 second wall-clock deadline
  terminates and reaps the worker and POSIX descendants.
- The entire JSON tool result is at most 32 KiB UTF-8. Text is stored once,
  truncated on a valid UTF-8 boundary, and reports original counts and
  truncation state.
- Source provenance contains MIME, byte size, dimensions, frame count, SHA-256,
  language selection, engine, and engine version; it does not expose a local
  path or filename.

## Registration and installation

The `builtin.ocr` plugin registers `extract_image_text` only after all gates:

1. `OCR_AGENT_TOOL_ENABLED=true`
2. `OCR_FILE_ROOT` or fallback `MULTIMODAL_FILE_ROOT`
3. optional Python packages from `requirements-ocr.txt`
4. system Tesseract binary and selected language packs

```bash
python -m pip install --constraint constraints.txt --build-constraint build-constraints.txt -r requirements-ocr.txt
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
The synthetic EN/ZH fixtures validate the safety envelope with injected engine
output. A real English Tesseract check remains optional when the host provides
the binary; this phase does not claim required Chinese/dense-table quality.

## Rollback

Set `OCR_AGENT_TOOL_ENABLED=false` and restart, or revert the PR. No database
migration or cleanup is required.
