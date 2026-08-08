# Multimodal Parsing (PDF & Chart) — Phase 1

StockPulse can parse financial PDFs into structured text/tables and read market
chart images into structured visual observations. This document describes
**phase 1** of issue #253: backend services plus optional, default-off Agent
Tools.

HTTP upload UI, report/prompt projection into the default analysis path,
scanned-PDF vision assist, and report evidence-chain projection remain later phases. Earnings-call transcript parsing is documented separately in `docs/earnings-transcript-parsing_EN.md` (tool `parse_earnings_transcript`).

## Honesty Contract

| Surface | Behavior |
| --- | --- |
| PDF | Local text extraction first. Empty/sparse PDFs return `unavailable` / `degraded` with a stable `reason_code` rather than inventing numbers. |
| Chart | Uses the existing `VISION_MODEL` path (same LiteLLM vision surface as image stock extraction). Missing model/keys return `unavailable` with an explicit reason. |
| Uploads | User files are never executed. Paths are sandboxed under `MULTIMODAL_FILE_ROOT`. Size caps and MIME/magic checks apply. |

Every successful or degraded payload includes a mandatory research-only disclaimer.

## Default And Registration Contract

Agent Tools `parse_financial_pdf`, `read_price_chart`, and
`parse_earnings_transcript` are **default-off**.

| Gate | Behavior |
| --- | --- |
| `MULTIMODAL_AGENT_TOOLS_ENABLED=false` (default) | Factory returns `None`; process tool registry unchanged |
| Enabled without `MULTIMODAL_FILE_ROOT` | Tools stay unregistered; warning logged |
| Both set, process restarted | Tools register in the cached `ToolRegistry` |
| Chart tool without vision readiness | Tool still registers; each call degrades with `vision_model_unavailable` / key errors |

Enabling requires a process restart so the cached tool registry rebuilds.

## Configuration

```bash
MULTIMODAL_AGENT_TOOLS_ENABLED=false
# MULTIMODAL_FILE_ROOT=/absolute/path/to/multimodal-uploads
# VISION_MODEL=openai/gpt-5.5   # used by chart reading when configured
```

## Services

| Module | Responsibility |
| --- | --- |
| `src/services/pdf_parsing_service.py` | Local PDF parse → `schema_version=pdf-parse-v1` |
| `src/services/chart_reading_service.py` | Vision chart read → `schema_version=chart-reading-v1` |
| `src/services/earnings_transcript_service.py` | Transcript parse → `schema_version=earnings-transcript-v1` |
| `src/agent/tools/multimodal_tools.py` | Default-off PDF/chart `ToolDefinition` factories |
| `src/agent/tools/earnings_transcript_tools.py` | Default-off transcript tool (separate from OCR) |

### PDF output (summary)

- `status` / `reason_code` / `method`
- `source` (filename, byte size, page count)
- `text`, `pages[]`, best-effort `tables[]`
- `vision_assist` reports `not_applicable` / `skipped` in phase 1 (no page rasterization)

### Chart output (summary)

- `chart_type`, `symbol_hints`, `timeframe_hint`, `trend`
- `key_levels[]`, `observations[]`, `confidence`
- `vision_model` when a route was selected

The chart prompt lives in `CHART_READ_PROMPT` and is documented in
`docs/chart-read-prompt.md`. Changing it requires updating that doc and
including the full prompt in the PR description (same house rule as
`EXTRACT_PROMPT`).

## Path Sandbox

- Relative paths resolve under `MULTIMODAL_FILE_ROOT`
- Absolute paths must remain inside the root after `resolve()`
- Rejected: `..` escapes, URLs, `~` expansion, null bytes, missing files
- Size caps: PDF 10 MiB, images 5 MiB (aligned with image stock extraction)

## Deferred (not phase 1)

- HTTP upload API pair / Web UI
- Automatic third-party earnings-transcript fetch
- Scanned-PDF page rasterization + vision assist
- Default analysis-path projection and report evidence chain wiring

Earnings-call **user-supplied** transcript parsing is available when multimodal
tools are enabled; see `docs/earnings-transcript-parsing_EN.md`.

## Rollback

1. Set `MULTIMODAL_AGENT_TOOLS_ENABLED=false` (or remove the variable)
2. Optionally clear `MULTIMODAL_FILE_ROOT`
3. Restart the process so the tool registry cache rebuilds without the tools

No database migration is involved.

## CI note

Phase 1 landings must keep the config-access and broad-exception ratchets green.
