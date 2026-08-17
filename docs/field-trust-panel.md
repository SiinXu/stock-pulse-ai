# Field-level data trust panel

Issue reference: #1129. Implementation lives in `src/data_provider/field_trust.py` with minimal wiring in `src/data_provider/base.py` and `src/data_provider/realtime_types.py`. The HTTP view is `GET /api/v1/stocks/{code}/trust`. The Web panel mounts on the stock workspace (`/stocks/<code>`).

## Contract

Per-field trust is additive metadata on the existing realtime quote fallback chain. It never replaces the primary observation and never silently picks one provider as truth when sources disagree.

| Surface | What it returns |
| --- | --- |
| Quote `field_trust` | schema, per-field source/origin/lag/staleness/conflict, conflict checks, provider attempts/health, analysis input |
| API `StockFieldTrustResponse` | `status` (`ok` / `degraded` / `unavailable`), the same field rows, conflicts, provider health, and `analysis_input` |
| Analysis input | provider-neutral `{ confidence, gaps[] }`; `high` only when every covered field is fresh, attributed, and conflict-free |
| Web panel | Visible degradation for stale, conflict, missing metadata, provider failure, and unavailable quotes |

`status=ok` is reserved for a complete, fresh, attributed, conflict-free view. Missing metadata, unknown staleness, skipped conflict checks, stale fields, conflicts, and preferred-provider failures are degradation signals.

## Ownership boundary vs #1133

This lane owns the trust contract only. The analysis projection is a stable, provider-neutral interface (`gaps` + `confidence`). It does not compile monitors, alert rules, or NL phrases.

## Compatibility

- `UnifiedRealtimeQuote.field_trust` is optional. Absent metadata must be read as unknown, never trusted.
- Quote `to_dict()` includes `field_trust` when present so analysis `_safe_to_dict(realtime_quote)` receives gaps/confidence.
- Recording helpers fail open for data (they never break the quote path) and fail closed for trust (missing payload is unknown).

## Rollback

Revert the introducing change. No configuration key is required; disabling `DATA_VALIDATION_ENABLED` records skipped conflict checks instead of implying agreement.
