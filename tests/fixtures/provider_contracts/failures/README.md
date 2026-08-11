# Provider failure-mode fixtures

Offline failure payloads used by `tests/data_provider/test_provider_fallback_contract.py`.

These are **shape-faithful** samples derived from the happy-path fixtures in the
parent directory (not live recordings). Collection date noted in each file's
`meta.recorded_note` (2026-08-08).

## Failure modes covered

| Mode | Files | Expected manager / parse behavior |
| --- | --- | --- |
| `empty` | `akshare_em_daily_empty.json`, `tencent_daily_kline_empty.json`, `tushare_daily_pro_empty_items.json` | Empty table / empty kline → provider attempt fails quality check; manager continues to next source |
| `missing_field` | `akshare_em_daily_missing_close.json`, `yfinance_daily_missing_volume.json` | Normalize/clean raises (typically `KeyError`); manager treats as provider exception and falls back |
| `format_error` | `tencent_daily_kline_malformed.json` | Parser returns no rows → empty daily frame |
| `rate_limit` | `tushare_daily_pro_rate_limit.json` | Tushare error body with quota/limit wording → `RateLimitError` → manager falls back |

Timeout is exercised via mocked `TimeoutError` (no payload file): a hung network
call has no stable body to freeze.

## Not network

All consumers must patch HTTP / SDK entry points. These fixtures must stay inside
`pytest -m "not network"`.
