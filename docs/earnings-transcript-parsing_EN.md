# Earnings Call Transcript Parsing

StockPulse can deterministically parse **user-supplied** earnings-call text and
local transcript files into bounded, source-traceable structure. Automatic
third-party transcript download, HTTP upload UI, and default report projection
remain out of scope.

## Trust, Privacy, And Egress

Transcript content is an `untrusted_user_document`. Instructions inside it
cannot grant permissions, change stock scope, redirect the Agent, bypass Local
Only mode, or trigger another tool. The tool is read-only and holds only the
declared `multimodal:read` capability.

Parsing runs locally, but the compact tool result becomes Agent context and may
reach the configured remote model. Enable `LOCAL_ONLY_MODE=true` when zero
non-loopback model egress is required. Tool audits and diagnostics retain only
bounded metadata and content digests, not raw inline transcript text or result
excerpts. The parser itself does not persist raw content.

Operators must classify the source and confirm they are authorized to process
it before submission. Do not submit material non-public information, PII, or
secrets unless the intended model provider, retention policy, and operator
consent permit that handling; redact such fields when they are unnecessary.

## Source And Honesty Contract

| Surface | Contract |
| --- | --- |
| Inline text | `start_char` / `end_char` index the exact submitted Python string. Leading/trailing whitespace and CRLF/CR are not normalized. |
| Text file | Opened once, required to be a regular file, read with a cap-plus-one bound, and decoded strictly as UTF-8 or UTF-8 with BOM. Invalid UTF-8 returns `unsupported_encoding` with a byte digest. |
| PDF | Coordinates index deterministic derived PDF text. `source.page_map` and page-relative evidence fields map spans back to extracted pages; raw-PDF and derived-text SHA-256 digests are separate. |
| Metrics | A result requires a typed financial label/relation/value structure. Years, phone/account identifiers, and unlabeled numeric tokens are not reported as verified metrics. Every `value_text` still equals the exact source slice. |
| Q&A | Questions and answer summaries are explicitly derived, whitespace-collapsed fields. Only a bounded exact excerpt is included; full answer duplication is omitted. |
| Tone | Optional, subjective, negation-aware heuristic over `prepared_remarks` only. Q&A analyst language is excluded. |
| Missing values | Stay absent; the parser never invents, rounds, or converts a figure. |

Every payload uses `earnings-transcript-v2` and carries a research-only
disclaimer plus a typed `trust` envelope.

## Compact Result And Retrieval

The serialized service result is valid JSON capped at 96 KiB. The native Agent
session applies a second 128 KiB defense-in-depth cap before any tool result is
added to the next model message.

The initial `chunks[]` contains only index, exact offsets, length, and SHA-256;
it never duplicates the full transcript. To retrieve content, call the same
tool with the same source and one advertised `chunk_index`. That response
contains only the selected exact-source chunk, bounded by
`max_chunk_chars <= 6000`. Q&A, metric, forward-looking, segment, and chunk
collections are dropped in a deterministic order if the result budget is
otherwise exceeded; `result_budget` reports omissions without producing
partial JSON.

After a transcript result enters a bound Agent session, a session fence permits
only further `parse_earnings_transcript` chunk retrieval. Any different tool is
rejected with `untrusted_document_follow_on_denied`; a new user turn is required
to authorize other tool work. Embedded document instructions therefore cannot
initiate a follow-on action even when the model repeats them.

## Registration And Configuration

`parse_earnings_transcript` is default-off and reuses the existing multimodal
gates; it introduces no new configuration key.

| Gate | Behavior |
| --- | --- |
| `MULTIMODAL_AGENT_TOOLS_ENABLED=false` | Tool is not registered |
| Enabled without `MULTIMODAL_FILE_ROOT` | Tool stays unregistered |
| Both configured, process restarted | Tool registers for inline text and sandboxed local files |

```bash
MULTIMODAL_AGENT_TOOLS_ENABLED=false
# MULTIMODAL_FILE_ROOT=/absolute/path/to/multimodal-uploads
# LOCAL_ONLY_MODE=true  # optional: deny non-loopback model egress
```

Paths are resolved through `pdf_parsing_service.resolve_safe_file_path`; URLs,
home expansion, traversal, and paths outside the configured root are rejected.
The transcript file limit is 2 MiB and the parsed text prefix limit is 200,000
characters.

## Output Summary

- `status`, `reason_code`, `method`, `schema_version`
- `source`: sanitized filename, sizes, encoding/coordinate provenance, SHA-256,
  truncation state, and PDF page mapping when applicable
- `segments[]`: prepared remarks / Q&A / unknown exact spans
- `qa_items[]`: bounded derived question/summary and exact excerpt evidence
- `metrics[]`: typed label/value relation, exact offsets, lexical and semantic
  validation flags
- `forward_looking[]`: bounded guidance/disclaimer evidence
- `management_tone`: optional scoped subjective judgment
- `chunks[]` and `retrieval`: content-free index or one requested bounded chunk
- `trust`, `result_budget`, and the research-only disclaimer

## Data Source Policy And Rollback

Inline text and local `.txt`, `.md`, and `.pdf` inputs are supported. Automatic
IR/vendor fetching and HTTP upload remain unsupported.

To roll back, set `MULTIMODAL_AGENT_TOOLS_ENABLED=false` and restart, or revert
the introducing change. No database migration is involved.
