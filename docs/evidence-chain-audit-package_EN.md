# Evidence Chain & Auditable Report Package

Conclusion→evidence chain and exportable audit package (Issues #986 / #127).
Read-only projections of persisted analysis history. Reuses reasoning-trace redaction
and the security-audit attempt/completion trail.

Chinese: [evidence-chain-audit-package.md](evidence-chain-audit-package.md)

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `EVIDENCE_CHAIN_ENABLED` | `true` | Build `evidence-chain-v1` |
| `AUDIT_EXPORT_ENABLED` | `false` | ZIP/JSON audit package export gate |
| `AUDIT_INCLUDE_RAW_ARTIFACTS` | `false` | Raw intermediates (still redacted); default skips with explicit marker |

When raw intermediates are enabled, the package contains only the persisted,
redacted `context_snapshot.json` and `raw_result.json`. Their combined hard limit
is 2,000,000 bytes. Missing or oversized data produces an explicit `MISSING`
artifact instead of silent omission.

## API

Requires administrator authentication.

```http
GET /api/v1/history/{record_id}/evidence-chain
GET /api/v1/history/{record_id}/evidence-pack?format=zip|json
GET /api/v1/analysis/{record_id}/evidence-chain
GET /api/v1/analysis/{record_id}/evidence-pack?format=zip|json
```

Both ZIP and JSON carry the manifest, report, evidence chain, reasoning trace,
decision signal, gaps, and raw-intermediate status. JSON exposes the same content
under `artifacts`; `evidence_chain.json` uses a `$ref` to the top-level
`evidence_chain` to avoid duplication. Uncompressed ZIP artifact content has a
hard 5,000,000-byte limit. Optional artifacts that do not fit are marked
`missing` in the manifest and set package `truncated=true`.

Security-audit events: `evidence_chain.export`, `audit_package.export`.

## Hard rules

1. No invented evidence.
2. Missing is explicit (`status=missing` / `gaps[]`), never omitted.
3. Redaction reuses `redact_export_payload` from reasoning-trace export.
4. Audit package embeds reasoning-trace via `build_reasoning_trace_package` (no parallel exporter).
5. Failed, timed-out, or unknown source/tool runs cannot support conclusions; they remain explicit missing evidence records.

## Rollback

Set `AUDIT_EXPORT_ENABLED=false` (and optionally `EVIDENCE_CHAIN_ENABLED=false`) and restart.
