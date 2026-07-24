# 06 Signal center

Path: **Signals** (often `/signals`).

Typical tabs:

| Tab | Purpose |
| --- | --- |
| Stream | Browse structured AI suggestions |
| Rules | Manage price, percent, indicator, and related alerts |
| Delivery history | Notification attempts after triggers |
| Review / stats | Outcome evaluation and summaries |

## Signal stream

1. Focus on **active** signals by default.
2. Filter by market, symbol, action, phase, source, and related fields.
3. Scope controls (when present) switch all / holdings / watchlist; delivery history and some stats may stay global.
4. Open a detail view for confidence, horizon, price plan, watch conditions, risk, and source report.
5. Mark closed, invalidated, or archived; terminal states usually cannot return to active directly.
6. Optionally mark useful / not useful.

**Interpretation**: signals are trackable advice records, not automated orders.

## Alert rules

1. Create a rule under **Rules**.
2. Choose a type (price cross, percent move, volume, indicators, portfolio risk, market status, and others as listed).
3. Set the target scope, save, and enable.
4. Prefer dry-run when available before long-running enablement.
5. Respect cooldown indicators to avoid notification spam.

## Delivery history and review

- Delivery history shows whether notifications were attempted and channel results.
- Outcome review is explicitly triggered from the UI when you want historical performance context.

Previous: [05 Agent chat](05-agent-chat_EN.md) · Next: [07 Portfolio](07-portfolio_EN.md)
