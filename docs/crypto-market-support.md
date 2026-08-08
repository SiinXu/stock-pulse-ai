# Cryptocurrency market support (Issue #236)

English technical contract for the optional crypto analysis module. Chinese
summary for operators lives in the same file’s “摘要” section below to keep a
single source of truth during the parallel batch.

## Summary / 摘要

- **Plan A**: `crypto` is added to `DATA_PROVIDER_MARKETS` and reuses the
  `DataProvider` contract (no parallel analysis pipeline).
- **Symbols**: only `crypto:TICKER` (e.g. `crypto:BTC`). Bare `BTC` / `ETH`
  are **not** auto-classified as crypto (collision with equity tickers).
- **Provider**: `CryptoCoingeckoFetcher` (CoinGecko public API, no key required
  for basic OHLC / simple price; optional `COINGECKO_API_KEY`).
- **Skill**: `strategies/crypto_market_structure.yaml` with
  `default_active: false` / `default_router: false`.
- **Default off**: manager auto-wiring is opt-in via
  `CRYPTO_PROVIDER_ENABLED` once the Integration Point in
  `data_provider/base.py` is applied (see below).

## 24×7 open / previous close definition

| Field | Definition used by this module |
| --- | --- |
| Daily bar date | **UTC calendar day** of the CoinGecko OHLC timestamp |
| Open | Open of that UTC daily candle |
| Previous close (`pre_close`) | Previous UTC daily close; for simple-price realtime quotes, implied from 24h percent change when CoinGecko does not return a session open |
| Trading calendar | **Not applicable** — do not use `src/core/trading_calendar.py` equity sessions for crypto |

## Equity dimensions explicitly bypassed

| Equity concept | Crypto handling |
| --- | --- |
| Exchange trading calendar / half-day | Always in-session for data purposes; no weekend gap logic |
| Limit-up / limit-down / limit-up pool | Unsupported; fetcher returns empty pool |
| PE / PB / earnings / dividends | Not applicable; specialist skill must say so instead of `N/A` walls |
| Chip distribution / northbound flow / dragon-tiger | Unsupported |
| A-share ST / board concepts | Unsupported |

## Data source research note

| Candidate | Key required? | Notes | Decision |
| --- | --- | --- | --- |
| **CoinGecko public API** | No (demo key optional) | OHLC + simple price; rate-limited; USD quotes | **Selected** for low-friction default stack |
| Binance public REST | No | Strong liquidity; exchange-specific; ToS/geo considerations | Deferred |
| Yahoo `BTC-USD` via yfinance | No | Reuses equity fetcher; weaker crypto semantics | Not primary |
| CoinMarketCap | Yes | Higher friction | Deferred |

## Integration Point (manager wiring)

`data_provider/base.py` is owned by a parallel task (T10) in the 2026-08-09
batch, so this module does **not** patch manager construction. After that
ownership clears, wire with:

```python
# Inside DataFetcherManager fetcher initialization, after optional fetchers:
from data_provider.crypto_coingecko_fetcher import attach_crypto_provider
import os
if os.getenv("CRYPTO_PROVIDER_ENABLED", "").strip().lower() in {"1", "true", "yes"}:
    attach_crypto_provider(self)
```

Until then, tests and custom hosts may call `attach_crypto_provider(manager)`
or use `build_crypto_provider_registration()` with the plugin registry.

Trading-calendar bypass for crypto symbols should likewise treat
`_market_tag(code) == "crypto"` as always tradeable when that file is next
opened by its owner.

## Configuration

```bash
# Default: crypto provider not auto-attached (no behavior change for equities)
CRYPTO_PROVIDER_ENABLED=false
# Optional CoinGecko demo/pro key (public endpoints work without it)
# COINGECKO_API_KEY=
# CRYPTO_COINGECKO_PRIORITY=10
```

## Rollback

Revert the introducing PR. No persistent crypto market data store is created.
