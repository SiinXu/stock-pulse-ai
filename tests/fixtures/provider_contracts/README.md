# Provider contract fixtures

Recorded (or shape-faithful) raw provider payloads used by offline contract tests
in `tests/data_provider/test_provider_contracts.py`.

## Purpose

Vendor response drift is otherwise only visible in the non-blocking nightly
`network-smoke` run. These fixtures freeze the **parse input shape** that analysis
consumes after each fetcher normalizes raw payloads into:

- Daily bars: `STANDARD_COLUMNS` = `date, open, high, low, close, volume, amount, pct_chg`
- Realtime quotes: `UnifiedRealtimeQuote` fields used by analysis / fallback routing
- Market routing: A-share SH/SZ/BJ symbol forms for Sina/Tencent/Tushare/Yahoo

Contract tests assert **shape, types, and routing**, not live prices.

## Layout

| File | Provider path | What the offline test feeds |
| --- | --- | --- |
| `akshare_em_daily.json` | AkShare Eastmoney `stock_zh_a_hist` | Chinese-column DataFrame → `_normalize_data` |
| `akshare_sina_daily.json` | AkShare Sina `stock_zh_a_daily` | English-column DataFrame → Sina rename → `_normalize_data` |
| `tencent_daily_kline.json` | Tencent `fqkline` JSON | Payload → `_extract_kline_rows` → `_normalize_data` |
| `tushare_daily_pro.json` | Tushare Pro `daily` HTTP body | `fields`/`items` → DataFrame → `_normalize_data` |
| `yfinance_daily.json` | Yahoo Finance history | Open/High/Low/Close/Volume → `_normalize_data` |
| `akshare_em_spot.json` | AkShare EM `stock_zh_a_spot_em` row | Cached snapshot → `get_realtime_quote(source="em")` |
| `akshare_sina_realtime.txt` | Sina `hq.sinajs.cn` text | Mocked HTTP body → Sina realtime parse |
| `akshare_tencent_realtime.txt` | Tencent `qt.gtimg.cn` text | Mocked HTTP body → Tencent realtime parse |
| `manifest.json` | Index of fixtures + expected contracts | Refresh script + humans |

## Refresh (network, not offline gate)

```bash
# Re-record into this directory (requires network + optional TUSHARE_TOKEN)
python scripts/refresh_provider_fixtures.py --write

# Write to a separate directory (nightly artifact path)
python scripts/refresh_provider_fixtures.py --output-dir /tmp/provider_contracts_refresh --skip-unavailable
```

Refresh is **manual or nightly only**. Do not run it inside `./scripts/ci_gate.sh` or
the blocking offline pytest suite. After a successful live refresh, review the
diff for shape changes (column renames, missing fields) before committing.

## Sanitization

Fixtures must never contain API tokens, cookies, or private endpoints. The
refresh script strips `token` fields from Tushare request metadata and only
persists response bodies / OHLCV tables.
