# Field-level data trust panel

Issue reference: #1129. Implementation lives in `src/data_provider/field_trust.py` with minimal wiring in `src/data_provider/base.py` and `src/data_provider/realtime_types.py`. The HTTP view is `GET /api/v1/stocks/{code}/trust`. The Web panel mounts on the stock workspace (`/stocks/<code>`). The exported `FieldTrustPanel` is also registered in the real playground catalog.

## Contract

Per-field trust is additive metadata on the existing realtime quote fallback chain. It never replaces the primary observation and never silently picks one provider as truth when sources disagree.

| Surface | What it returns |
| --- | --- |
| Quote `field_trust` | schema, per-field source/origin/lag/staleness/conflict, conflict checks, provider attempts/health, analysis input |
| API `StockFieldTrustResponse` | `status` (`ok` / `degraded` / `unavailable`), the same field rows, conflicts, provider health, and `analysis_input` |
| Analysis input | provider-neutral `{ confidence, gaps[] }`; `high` only when every covered field is fresh, attributed, and conflict-free. `AnalysisContextBuilder` copies a bounded `{confidence, conflict_count, gap_codes, failed_provider_count}` into quote-block metadata. A non-high payload (conflict, stale, unattributed, provider failure, skipped comparison, or missing/legacy metadata) maps the quote block to `partial` (or keeps `stale`/`fallback`) so the existing core-degraded rule forbids `confidence_level=High`. The full `field_trust` blob is not copied as a quote item. |
| Report summary | Jinja analysis reports (`templates/report_markdown.j2`, plus wechat/brief when the same report renderer runs) render a small source / confidence / gap / conflict-count summary from that bounded pack metadata. The public overview quote block already carries `source`, `status`, and `quote_trust_*` warnings; reports reconstruct the same gaps and never re-fetch `/trust` or `get_realtime_quote`. A fresh conflict-free quote stays `confidence=high` with empty gaps. Missing overview omits the section instead of inventing degradation. |
| Web report page | `AnalysisContextSummary` localizes the same overview quote `source` / `status` / `quote_trust_*` warnings into a low-sensitivity quote-trust line. It never mounts full `field_trust`, provider attempts, or circuit blobs. |
| Web panel | Visible degradation for stale, conflict, missing metadata, provider failure, and unavailable quotes |

`status=ok` is reserved for a complete, fresh, attributed, conflict-free view whose provider-health rows are all `ok`. Missing metadata, unknown staleness, skipped conflict checks (including a comparison that failed closed), stale fields, conflicts, preferred-provider failures, later-source empty/failed/unavailable supplement attempts, and a circuit snapshot with `available=false` are degradation signals. They must not coexist with `status=ok` or analysis `confidence=high`. Cross-source identities use the same source tokens as field attribution (`efinance`, `akshare_em`), not fetcher class names. Provider-health rows keep those public tokens but look up circuit snapshots by the exact route/circuit key carried on the attempt, so a CN `akshare_em` row cannot inherit an ETF or HK circuit. The Web panel localizes known status and gap codes from `FIELD_TRUST_TEXT`; backend English `message`/`detail` strings are not preferred over that copy.

## Ownership boundary vs #1133

This lane owns the trust contract only. The analysis projection is a stable, provider-neutral interface (`gaps` + `confidence`). It does not compile monitors, alert rules, or NL phrases.

## Compatibility

- `UnifiedRealtimeQuote.field_trust` is optional. Absent metadata must be read as unknown, never trusted.
- Quote `to_dict()` includes `field_trust` when present. Analysis consumption is through `_to_dict(realtime_quote)` plus the bounded `analysis_input` projection; receiving the nested object is not the same as treating it as trusted.
- Recording helpers fail open for data (they never break the quote path) and fail closed for trust (missing or legacy payload is unknown, never `high`).

## Rollback

Revert the introducing change. No configuration key is required; disabling `DATA_VALIDATION_ENABLED` records skipped conflict checks instead of implying agreement.
