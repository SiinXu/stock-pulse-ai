# Research Timeline (Per-Symbol)

## Purpose

Stock Details (`/stocks/:stockCode`) exposes a **Research timeline** card that
aggregates research activity for one symbol:

| Kind | Source | Deep link |
| --- | --- | --- |
| `analysis_run` | `analysis_history` | Analysis workbench history (`recordId`) |
| `chat` | User turns with `context_json.stock_code` | `/chat?session=…` (turn identity from #923) |
| `signal` | `decision_signals` | Signal Center with stock context |
| `hypothesis` | Optional #1130 workspace | Unavailable until that workspace ships |

## API

```http
GET /api/v1/stocks/{stock_code}/research-timeline?cursor=&limit=20&kinds=
```

- **Cursor pagination**: each page overscans at most `limit` rows **per source**,
  merges by `occurred_at` DESC, and returns `next_cursor` / `has_more`.
  Clients must not request an unbounded full history dump.
- **Honest empty / unavailable**:
  - `sources.*.empty` — source is implemented but has no rows for this symbol
  - `sources.hypothesis.unavailable` — hypothesis workspace is not installed
  - The UI surfaces these distinctions instead of a false “all clear” empty.

## Analysis compare

Selecting two `analysis_run` nodes shows a simple direction + confidence compare.
This is intentionally narrow (not a full report diff).

## Related

- Issue #1137 (feature), #1127 (innovation epic)
- Hypothesis workspace #1130 (timeline input when present)
- Chat turn identity #923
