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

## API

Requires administrator authentication.

```http
GET /api/v1/history/{record_id}/evidence-chain
GET /api/v1/history/{record_id}/evidence-pack?format=zip|json
GET /api/v1/analysis/{record_id}/evidence-chain
GET /api/v1/analysis/{record_id}/evidence-pack?format=zip|json
```

Security-audit events: `evidence_chain.export`, `audit_package.export`.

## Hard rules

1. No invented evidence.
2. Missing is explicit (`status=missing` / `gaps[]`), never omitted.
3. Redaction reuses `redact_export_payload` from reasoning-trace export.
4. Audit package embeds reasoning-trace via `build_reasoning_trace_package` (no parallel exporter).

## Rollback

Set `AUDIT_EXPORT_ENABLED=false` (and optionally `EVIDENCE_CHAIN_ENABLED=false`) and restart.
