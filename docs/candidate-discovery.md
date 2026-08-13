# Bounded AI Candidate Discovery

- Status: `Living`
- Last verified: 2026-08-12
- Related: Issues #177, #325; [中文版](candidate-discovery_CN.md); [AlphaSift integration](alphasift-integration.md)

## Purpose

Add **AI discovery** to the existing Research Discover screening page without creating a new route. Users can shortlist candidates from an **explicit, paginated universe** using natural language or structured criteria, then hand off to full analysis or the watchlist.

**Product boundary:** “full-market” in this v1 means *paginated stock-index / watchlist / portfolio universes with hard provider budgets*, not AlphaSift’s full-market snapshot scan. AlphaSift strategy mode remains available for users who enable it.

## Non-goals

- Unbounded full-market quote scans
- Replacing AlphaSift strategy screening (still available as the Strategy mode)
- Trade instructions or portfolio optimization

## Universes

| Universe | Source | Pagination |
| --- | --- | --- |
| `watchlist` | Configured stock list | page / page_size |
| `portfolio` | Cached holdings | page / page_size |
| `index` | Local stock index (`stocks.index.json`) | page / page_size |
| `codes` | Explicit request codes (max 100) | single page |

Hard caps per run:

- max results: 30 (default 10)
- page size: 100
- symbols evaluated: 200
- data_provider quote calls: 50 (default 20)
- optional LLM explain calls: 1 batch (max 2 budget)

## API

- `POST /api/v1/discover/screen` — synchronous discovery
- `POST /api/v1/discover/screen/tasks` — background task (202)
- `GET /api/v1/discover/screen/tasks/{task_id}`
- `POST /api/v1/discover/screen/tasks/{task_id}/cancel`

Responses include:

- `candidates[]` with `reason` / `reason_codes` (and optional `llm_thesis`)
- `universe_contract` (resolved / filtered / evaluated counts, truncation)
- `cost_contract` (provider calls, LLM calls, elapsed_ms, bounded flag)
- `research_disclaimer`

## Data path

1. Resolve universe page (local index / watchlist / portfolio — no full-market scan).
2. Apply NL → criteria rules (markets, keywords, change/amount thresholds, ST exclusion).
3. Fetch quotes only within `max_provider_calls` via `DataFetcherManager` (`data_provider`).
4. Score, rank, return explainable shortlist; optional LLM batch polish when enabled.
5. Cancel checks between symbols when running as a task.

## Web

Research Discover (`/research/discover`) mode toggle:

- **AI discovery**: NL/criteria panel, cancel, cost summary, analyze + add-to-watchlist
- **Strategy screen**: existing AlphaSift strategy flow (requires `ALPHASIFT_ENABLED`)

Strategy screen remains the initial mode for backward compatibility. AI discovery is directly reachable from the mode control without enabling AlphaSift.

Discovery UI copy uses a feature-owned inventory. The eight translated locale packs are loaded on demand, are real localized copy rather than identical-English baseline entries, and remain `PENDING_NATIVE_REVIEW` for financial-language review.

The page header stays mode-aware: discovery mode reports “AI discovery ready (bounded)” and does **not** require AlphaSift to be enabled.

## Rollback

Revert the PR, or stop calling `/api/v1/discover/*` and hide the AI discovery mode on the screening page. No migration and no new required env vars.
