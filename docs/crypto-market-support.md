# Cryptocurrency market support (Refs #236 and #195)

This document defines the delivered, default-off CoinGecko market-data slice.
It does not claim completion of the broader product issues.

## Summary / 摘要

- **Plan A**: `crypto` is added to `DATA_PROVIDER_MARKETS` and reuses the
  `DataProvider` contract (no parallel analysis pipeline).
- **Symbols**: only `crypto:TICKER` (e.g. `crypto:BTC`). Bare `BTC` / `ETH`
  are **not** auto-classified as crypto (collision with equity tickers).
- **Provider**: `CryptoCoingeckoFetcher` (CoinGecko keyless, Demo, or Pro API).
- **Skill**: `strategies/crypto_market_structure.yaml` with
  `default_active: false` / `default_router: false`.
- **Default off**: `CRYPTO_PROVIDER_ENABLED=true` registers exactly one declared
  crypto provider in each newly created production manager.

## 24×7 open / previous close definition

| Field | Definition used by this module |
| --- | --- |
| Daily bar date | **UTC calendar day**, derived from exact `/market_chart/range` observations |
| Open / high / low / close | First / maximum / minimum / last finite observation for that UTC date |
| Realtime rolling change | `change_pct` is rolling 24h; `pre_close` stays empty because it is not a previous UTC-day close |
| Realtime amount | USD rolling-24h trading value; asset-unit `volume` stays empty |
| Trading calendar | Always open, 24×7, UTC; no equity exchange calendar |

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

## Provider, identity, and request contract

- The public identity is `crypto:TICKER`; supported tickers come from a
  versioned allowlist. Unknown or ambiguous ticker text fails explicitly.
- Historical requests send the exact inclusive UTC start/end interval to
  `/market_chart/range`, filter the response again, and emit one row per UTC date.
- Every HTTP request uses the shared outbound policy, including Local Only,
  DNS/redirect/response-size controls, and cross-origin credential stripping.
- 429 and transient failures have a bounded three-attempt retry and short
  cooldown. A failed crypto provider does not invoke equity providers.
- Daily provenance columns include market, USD currency, CoinGecko source,
  UTC-day granularity, close timestamp, completeness, and observation count.

## Configuration

```bash
# Default: crypto provider not auto-attached (no behavior change for equities)
CRYPTO_PROVIDER_ENABLED=false
# keyless | demo | pro
COINGECKO_API_PLAN=keyless
# COINGECKO_API_KEY=
# Custom HTTPS bases are permitted only in keyless mode.
# COINGECKO_API_BASE=
# CRYPTO_COINGECKO_PRIORITY=10
```

Demo mode uses `https://api.coingecko.com/api/v3` with
`x-cg-demo-api-key`. Pro mode uses `https://pro-api.coingecko.com/api/v3`
with `x-cg-pro-api-key`. Keys are rejected for custom origins.

## 中文运维契约

- 仅接受显式命名空间 `crypto:TICKER`；裸 `BTC` / `ETH` 仍按股票代码处理。
- `CRYPTO_PROVIDER_ENABLED=true` 后，新建的生产 manager 只注册一个声明为
  `crypto` 市场的 CoinGecko provider；关闭后不注册，不会调用股票 provider。
- 历史数据使用精确 UTC 起止区间，并再次过滤、排序、去重；每天只输出一条
  有限且满足 OHLC 约束的日线。来源、币种、粒度、收盘时间和完整性随数据保留。
- 实时报价币种为 USD；`amount` 表示滚动 24 小时美元成交额，`volume` 不冒充
  币数量，滚动 24 小时涨幅也不冒充“昨收”。
- 所有请求统一经过出站安全策略；Local Only、SSRF、重定向、DNS 重绑定和响应
  大小限制均保持 fail-closed。429 仅做有界重试和短暂冷却。
- 加密市场按 UTC 24×7 开放；PE/PB、财报、涨跌停、筹码、龙虎榜、北向资金等
  股票专属维度明确标记为不适用。
- Keyless 不配置 key；Demo 和 Pro 分别使用官方域名与对应请求头，凭据不会发送
  到自定义或跨域地址。配置变更需要重启后生效。

## Rollback

Revert the introducing PR. No persistent crypto market data store is created.
