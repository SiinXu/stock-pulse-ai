# Prediction `resolve_after` trading-calendar policy

Issue **#1109** (Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107) Agent Evolution A6).

This document defines how the forecast-verification track converts a horizon into a UTC `resolve_after` timestamp, including A-share / Hong Kong / US session, timezone, holiday, and early-close rules. Implementation:

- Module: `src/core/prediction_resolve_after.py`
- Entry point: `compute_resolve_after(market, created_at, horizon, as_of_policy=...)`
- Reuses: `src.core.trading_calendar` (`MARKET_EXCHANGE` / `MARKET_TIMEZONE` / `get_effective_trading_date` / `exchange-calendars`)

**Hard rule: never approximate trading days with natural calendar days.** When the exchange calendar is unavailable, computation fails closed with `CalendarUnavailableError` (`calendar_approx` is always `false`). Upstream must treat this as `data_unavailable` / retry — never invent a due time.

中文版：[prediction-resolve-after.md](prediction-resolve-after.md)

---

## Scope

| In scope | Out of scope |
| --- | --- |
| Horizon → UTC `resolve_after` | Persisting `PredictionRecord` (#1101 / #1112) |
| Skipping weekends/holidays via exchange sessions | Actuals fetch and scoring (#1110 / #1111) |
| Early closes via real `session_close` | Scheduler tick / batch resolver (#1116 / #1104) |
| Cross-market rules | Runtime mutation of Soul / ToolSurface |

Product rules from Epic #1107: system-driven verification; research/quality-ops framing only; provider failure → `data_unavailable`/retry, never a fabricated hit.

---

## API contract

```python
from src.core.prediction_resolve_after import compute_resolve_after, AsOfPolicy

result = compute_resolve_after(
    market="cn",                          # authoritative region: cn | hk | us | …
    created_at=created_at_utc,            # prefer aware; naive is treated as UTC
    horizon="5d",                         # Nd trading sessions, or a positive int
    as_of_policy=AsOfPolicy.TRADING_DAY_CLOSE,
    stock_code="600519",                  # optional consistency check vs market
    allow_cross_market=False,
)
# result.resolve_after  -> timezone-aware UTC datetime
# result.to_dict()      -> safe for model_meta / diagnostics
```

### `as_of_policy`

| Policy | Meaning |
| --- | --- |
| `trading_day_close` (default) | Advance **N exchange sessions**, set `resolve_after` to that session’s **close** in UTC |
| `explicit_timestamp` | Horizon is absolute (`datetime` / ISO string / bare `date` → 00:00 UTC); no session math |

### Horizon semantics (`trading_day_close`)

1. **Anchor session**: `get_effective_trading_date(created_at)` — the latest **completed** trading session (intraday → previous session; after close → current session; non-trading day → previous session). Matches completed daily-bar semantics used by analysis and DecisionSignal outcomes.
2. **Target session**: `session_offset(anchor, N)` — the N-th exchange session **after** the anchor (`1d` / `5d` / `20d`, …).
3. **`resolve_after`**: target session `session_close`, stored as UTC.

So `1d` is **not** “calendar day + 1”; it is “after the next trading session close.”

Unsupported under `trading_day_close`: `swing` / `long` / free-form prose; crypto. For crypto or free-form market keys, use `as_of_policy=explicit_timestamp` (session math is skipped; `calendar_approx` remains false).

---

## Markets, timezones, exchange codes

| Market key | Exchange (`exchange-calendars`) | IANA timezone | Typical local close (indicative) |
| --- | --- | --- | --- |
| `cn` | `XSHG` | `Asia/Shanghai` | 15:00 |
| `hk` | `XHKG` | `Asia/Hong_Kong` | 16:00 |
| `us` | `XNYS` | `America/New_York` | 16:00 (DST-safe via UTC storage) |

Implementation reuses `trading_calendar.MARKET_EXCHANGE` / `MARKET_TIMEZONE` — no parallel holiday tables. JP/KR/TW work when registered in that module; #1109 acceptance focuses on **CN / HK / US**.

---

## Holidays, weekends, half-days

| Case | Behavior |
| --- | --- |
| Weekend | `session_offset` only lands on exchange sessions |
| Holiday (CN National Day, US Thanksgiving, HK Christmas, …) | Closed days are not sessions; N-session advance skips them |
| Half-day / early close (e.g. US Jul 3, HK Dec 24) | Uses the calendar’s real `session_close`; sets `is_early_close=true` |
| US DST | Local close converted through `America/New_York` to UTC |

**Forbidden**: `created_at + timedelta(days=N)`, generic business-day approximations, or a natural-day fallback with `calendar_approx=true` when the calendar fails.

---

## Cross-market symbol rules

1. **`market` is authoritative** for session math; do not infer the market only from the server’s local timezone.
2. **Optional `stock_code` check**: if the code resolves to a different market than `market`, raise `CrossMarketMismatchError` unless `allow_cross_market=True` (e.g. ADR / dual-listed symbols where the caller deliberately picks one venue).
3. **Never mix calendars**: HK symbols must not advance on `XSHG`; US symbols must not use A-share holiday tables.
4. **Multi-symbol portfolios**: each prediction computes its own `resolve_after` on its own market; due scans compare each UTC timestamp independently.
5. **Bare-code ambiguity**: six-digit defaults to A-share at the symbol layer ([market-support.md](market-support.md)); resolve-after does not second-guess.

---

## When the calendar is unavailable

| Condition | Result |
| --- | --- |
| `exchange-calendars` not installed | `CalendarUnavailableError` / `calendar_unavailable` |
| Exchange load failure / session out of range | `CalendarUnavailableError` with a specific `error_code` |
| Unsupported market / crypto + `trading_day_close` | `UnsupportedMarketError` |
| Invalid horizon | `InvalidHorizonError` |

Upstream (contract write, persistence, scheduler) must:

- not write a fabricated `resolve_after`;
- record `data_unavailable` or defer pending creation;
- retry after the calendar is available.

The original issue text mentioned a natural-day fallback with `calendar_approx=true`. **This repository rejects that fallback** so it never fabricates a due time.

---

## Difference from DecisionSignal expiry

| | Prediction `resolve_after` (this module) | DecisionSignal `expires_at` |
| --- | --- | --- |
| Daily horizons | **Exchange session** counts | Some paths still use natural-day TTL (legacy display) |
| Purpose | When actuals may be fetched and scored | When a signal card expires in the UI |
| Calendar failure | Fail closed | Existing fallback TTL |

DecisionSignal **outcome** evaluation already counts `StockDaily` trading bars; this module aligns with that **session** semantics, not the display-only natural-day expiry path.

---

## Verification

```bash
python -m pytest tests/core/test_prediction_resolve_after.py -q
```

Coverage: CN weekend/National Day, HK Christmas/half-day, US Thanksgiving/early close/cross-timezone/DST, calendar fail-closed, cross-market checks.

---

## Rollback

Revert the commit that added `src/core/prediction_resolve_after.py` plus matching tests/docs. No DB migration, no config keys, no user-data backfill.
