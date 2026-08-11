# Valuation Models (DCF & Relative) — Phase 1

StockPulse can estimate intrinsic value with a transparent DCF model and peer
relative valuation (P/E, P/B). This document covers issue #238: backend valuation service, optional default-off
Agent Tool, report/prompt projection, EV/EBITDA when explicit inputs exist, and
the interactive Web DCF sensitivity UI.

## Honesty Contract

Every estimate:

- carries **explicit assumptions** (growth, discount, terminal growth, horizon,
  cash-flow source, peer set);
- includes a **growth × discount sensitivity range** for DCF equity value;
- returns `insufficient_fundamentals` when required inputs are missing — it
  **never fabricates** a cash-flow base, peer multiple, or intrinsic price.

The mandatory disclaimer states that results are research support only and are
not investment advice.

## Default And Registration Contract

The Agent Tool `estimate_stock_valuation` is **default-off**.

| Gate | Behavior |
| --- | --- |
| `VALUATION_AGENT_TOOL_ENABLED=false` (default) | Factory returns `None`; the process tool registry does not include the tool |
| `VALUATION_AGENT_TOOL_ENABLED=true` | After process restart, `build_valuation_tool(config)` registers the tool |
| Multi-agent Risk Agent | Exposes the tool only when it is present in the process registry |
| Single-agent / full registry | Tool is available with the rest of the catalog when registered |

Enabling the flag requires a process restart so the cached tool registry can
rebuild. Default analysis, reports, notifications, Docker, and desktop packages
continue unchanged when the flag is off.

## Data Boundary

Fundamentals and quotes are consumed **only** through existing
`DataFetcherManager` interfaces (`get_fundamental_context`,
`get_realtime_quote`). Phase 1 does not add fetcher files or bypass provider
fallback.

Cash-flow priority for DCF:

1. Positive `operating_cash_flow` from the earnings block
2. Else positive `net_profit_parent` as an explicit proxy (source recorded)
3. Else `insufficient_fundamentals`

Growth defaults to the more conservative of revenue / net-profit YoY when
available (capped), otherwise a documented constant. Callers may override
growth, discount, terminal growth, and projection years.

## DCF Model

Two-stage structure:

1. Project free cash flow for `projection_years` at the high-growth rate
2. Terminal value via Gordon growth: `FCF_{n+1} / (r - g_term)`
3. Discount projected FCF and terminal value at the discount rate
4. When net debt is unavailable, equity value equals enterprise value and that
   assumption is stated

Sensitivity table: growth deltas `{-2pp, 0, +2pp}` × discount deltas
`{-1pp, 0, +1pp}` of equity value, with terminal growth kept strictly below each
scenario discount rate.

## Relative Valuation

- Target P/E and P/B from fundamental / quote data
- Optional peer codes (comma-separated); medians of **positive** peer multiples
- Implied prices: `EPS × peer PE median`, `book/share × peer PB median`
- Empty peers or missing multiples → `insufficient_fundamentals` for the
  relative section (no invented peer set)
- EV/EBITDA is estimated **only** when explicit `ebitda`, positive `market_cap`/`total_mv`,
  and explicit `net_debt` (may be zero/negative net cash) are available. Missing inputs
  yield `insufficient_fundamentals` for EV/EBITDA; total liabilities are never a debt proxy.

## Tool Input / Output

| Field | Contract |
| --- | --- |
| `stock_code` | Required; stock-scoped; same portable codes as other market tools |
| `growth_rate` | Optional decimal; omit to auto-derive from fundamentals |
| `discount_rate` | Optional decimal; default `0.10` |
| `terminal_growth_rate` | Optional decimal; default `0.03`; must be `< discount_rate` |
| `projection_years` | Optional integer `1..15`; default `5` |
| `peer_codes` | Optional comma-separated peer codes |

Output schema version: `valuation-estimate-v1`.

Top-level fields include `status` (`ok` / `partial` / `insufficient_fundamentals`),
`dcf`, `relative`, `fundamentals_snapshot`, and `disclaimer`. Each model section
embeds its own `assumptions` and, for DCF, `sensitivity`.

Policy: read-only, `market_data:read`, stock scope, `enforce_contract=True`.

## Configuration

```bash
# .env — default off
VALUATION_AGENT_TOOL_ENABLED=false
```

Web Settings → Agent shows the same switch. Save + restart required for
registration.

## Verification

```bash
python -m py_compile src/services/valuation_service.py src/agent/tools/valuation_tools.py
python -m pytest tests -k "valuation or dcf" -m "not network and not benchmark"
```

## Report / prompt projection

- Optional `dashboard.valuation` or `extra_context.valuation_by_code[code]` renders a valuation section.
- Missing valuation omits the section (no empty placeholders).
- `format_valuation_prompt_block(estimate)` for analysis-context / LLM injection.

## Web sensitivity UI

- `DcfSensitivityPanel` + `GET|POST /api/v1/valuation/estimate`
- Consumes server-side sensitivity rows; assumptions visible/adjustable; non-advice disclaimer.
- Playground: `dcf-sensitivity-panel`. StockDetailsPage integration deferred (frozen page).

## Remaining follow-ups

- Market-specific model packs beyond shared DCF / PE-PB / EV-EBITDA
- Auto-attach valuation into default analysis dashboard during pipeline runs

## Rollback

1. Set `VALUATION_AGENT_TOOL_ENABLED=false` (or remove the variable)
2. Restart the process
3. The tool disappears from the registry; analysis paths remain unchanged
