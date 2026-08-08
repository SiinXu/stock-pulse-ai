# Earnings Call Transcript Parsing

StockPulse can parse **user-supplied** earnings-call transcripts into structured
segments, Q&A turns, and **source-traceable** metrics. This is the remaining
backend capability from issue #253 after phase 1 PDF/chart landing (PR #844).

Automatic download of third-party transcript providers, HTTP upload UI, and
default analysis-path / report evidence-chain projection remain **out of scope**
for this module.

## Honesty Contract

| Surface | Behavior |
| --- | --- |
| Metrics | Every `value_text` is an exact substring of the source with `start_char` / `end_char`. Failed spans are dropped. |
| Missing numbers | Stay empty — never invented, rounded, or unit-converted into a new figure. |
| Management tone | Optional keyword heuristic; always tagged `judgment: subjective`. |
| Paths | Sandboxed under `MULTIMODAL_FILE_ROOT` via the shared `resolve_safe_file_path` helper. |

## Reuse Of PDF Parsing

| Concern | Approach |
| --- | --- |
| Path sandbox | Reuses `pdf_parsing_service.resolve_safe_file_path` |
| PDF transcript files | Text extracted with `parse_pdf_bytes`, then fed into the transcript pipeline (`method=pdf_then_transcript`) |
| Chunking | Transcript-specific character windows (`MAX_CHUNK_CHARS=6000`, overlap 200) — oral text is not page-oriented |

Structured Q&A / metric extraction is **not** a copy of the PDF table heuristic;
it is a dedicated deterministic pipeline for long oral transcripts.

## Default And Registration Contract

Agent Tool `parse_earnings_transcript` is **default-off** and reuses the phase 1
multimodal gates (no new config-registry keys):

| Gate | Behavior |
| --- | --- |
| `MULTIMODAL_AGENT_TOOLS_ENABLED=false` (default) | Factory returns `None`; process registry unchanged |
| Enabled without `MULTIMODAL_FILE_ROOT` | Tool stays unregistered |
| Both set, process restarted | Tool registers beside PDF/chart tools |

Tool name and module are intentionally separate from OCR tools:

| Item | Value |
| --- | --- |
| Tool name | `parse_earnings_transcript` |
| Module | `src/agent/tools/earnings_transcript_tools.py` |
| Service | `src/services/earnings_transcript_service.py` |
| Schema | `earnings-transcript-v1` |

## Configuration

```bash
MULTIMODAL_AGENT_TOOLS_ENABLED=false
# MULTIMODAL_FILE_ROOT=/absolute/path/to/multimodal-uploads
```

## Output (summary)

- `status` / `reason_code` / `method`
- `source` (filename, char/byte size, input mode)
- `segments[]` — `prepared_remarks` / `qa` / `unknown` with offsets
- `qa_items[]` — questioner, topic, question/answer text, offsets, excerpt
- `metrics[]` — `value_text`, offsets, optional label, `category`, `source_verified`
- `forward_looking[]` — guidance / disclaimer sentences with offsets
- `management_tone` — optional subjective label
- `chunks[]` — bounded windows for prompt assembly (`char_count <= max_chunk_chars`)

## Data Source Policy (v1)

| Mode | Supported |
| --- | --- |
| Inline `text` tool parameter | Yes |
| Local `.txt` / `.md` under file root | Yes |
| Local `.pdf` under file root (via PDF text extract) | Yes (best-effort) |
| Automatic fetch from IR / third-party APIs | **No** (remaining scope) |
| HTTP upload API / Web UI | **No** (remaining scope) |

## Rollback

1. Set `MULTIMODAL_AGENT_TOOLS_ENABLED=false` and restart, or
2. Revert the PR that introduced the service/tool.

No database migration is involved.
