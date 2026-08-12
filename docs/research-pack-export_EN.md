# Research Pack Export

One-click export of a portable research asset package (Issues #988 / #1140).
Assembled from already-persisted analysis history. Chinese: [research-pack-export.md](research-pack-export.md).

## Package layout (`research-pack-v1`)

```
research-pack-{code}-{date}/
├── meta.json
├── report.md
├── brief-card.md
├── signals.json
├── evidence-refs.json
├── evidence-summary.md
├── claims-outcomes.json
├── reasoning-trace.json
└── README.md
```

Full `evidence-chain-v1` (#986/#127) is **deferred**; `meta.evidence_chain_status=deferred`.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `RESEARCH_PACK_EXPORT_ENABLED` | `false` | Master switch |
| `RESEARCH_PACK_MAX_ZIP_BYTES` | `25165824` | ZIP upper bound (1–64 MiB) |

## API

```http
GET /api/v1/history/{record_id}/research-pack?format=zip|json&language=en|zh
```

Requires administrator authentication. Headers: `X-Research-Pack-Schema`, `Truncated`, `Bytes`, `Progress`. Security audit event: `research_pack.export`.

## Security

Share-mode redaction is always on via `redact_export_payload`. Counterexample tests cover API keys, bearer tokens, local paths, and credential URLs.

## Rollback

Set `RESEARCH_PACK_EXPORT_ENABLED=false` and restart.
