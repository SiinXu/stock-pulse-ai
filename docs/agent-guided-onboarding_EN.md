# Agent-guided onboarding

Related issue: [#589](https://github.com/SiinXu/stock-pulse-ai/issues/589)

## Purpose

Guide first-time users through a short **profile intake** → **config plan preview** → **confirm apply** flow without dumping the full Settings surface. The plan teaches product setup and research workflows; it never places buy/sell orders and never invents API keys.

## Entry points

| Entry | Behavior |
| --- | --- |
| Home incomplete-setup card | Primary CTA **Let the assistant configure this**; secondary **Open Settings manually** |
| First-run wizard final step | Optional **Continue agent-guided setup** after a successful minimal save |
| Later | Re-open from Home when setup is incomplete (skip/resume via local draft) |

Skippable at every step. Intake answers are stored in `localStorage` as a draft so the flow is resumable.

## Profile schema (`UserOnboardingProfile`)

Versioned JSON (`schema_version = 1`):

| Field | Values |
| --- | --- |
| `experience_stage` | `beginner` / `report_reader` / `has_system` |
| `markets` | multi: `cn` / `hk` / `us` |
| `goals` | multi: `daily_push` / `pre_post_market` / `holdings_risk` / `strategy_validation` |
| `holdings` | `none` / `watchlist` / `bookkeeping` |
| `interaction` | `push` / `web` / `chat` |
| `risk_tone` | `conservative` / `balanced` / `assertive` (tone only) |
| `infrastructure` | `cloud_key` / `local_models` / `free_only` |
| `report_language` | `zh` / `en` / `ko` |

## Plan engine honesty

- **Default engine:** deterministic rules (`engine: "rules"`).
- **LLM refinement:** only meaningful when a model is already available *and* the user opts in. If no model is available, the response stays rule-based with an honest `llm_note` — never fake AI.
- **Presets:** prefers official preset maps from W10-03 (`src.services.config_presets`) when present; otherwise uses aligned built-in fallback maps (`local-first`, `cli-backends`, `cloud-balanced`, `power-user`).

## Apply contract

- Writes **non-secret** keys only through `SystemConfigService.update`.
- Secrets (API keys, tokens, passwords) are **never** written; the plan returns todos with Settings deep links.
- Empty `STOCK_LIST` may receive a market-based seed (for example `600519`, `hk00700`, `AAPL`); existing lists are left untouched.
- After apply, state is persisted next to the active `.env` as `onboarding_state.json` (profile + last plan). Reset deletes the profile only; config writes are kept.

## Feature stages (L0–L3)

| Stage | Emphasis | Defer |
| --- | --- | --- |
| L0 cold start | Home, analysis workbench, model/watchlist settings | Full Signal center, committee, plugins |
| L1 daily reader | History, market review, notifications | Complex alert rules |
| L2 holdings | Portfolio, basic price alerts | Multi-Agent, custom Skills |
| L3 research | Chat, signals, backtest | High-cost committee default-off |

Stages affect recommended plan copy and Home “today’s plan” card. Routes are not hard-deleted.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/onboarding/plan` | Generate plan |
| `POST` | `/api/v1/onboarding/apply` | Apply non-secret config + persist profile |
| `GET` | `/api/v1/onboarding/state` | Load persisted state |
| `DELETE` | `/api/v1/onboarding/state` | Reset profile/plan (keep config) |

## Disclaimer

StockPulse onboarding teaches configuration and research product paths. It is **not** investment advice and does not issue mandatory buy/sell steps.

## Rollback

- Close or hide the onboarding entry points (Home CTA / wizard button).
- Delete `onboarding_state.json` or call `DELETE /api/v1/onboarding/state`.
- Already written non-secret config remains until manually changed in Settings.
