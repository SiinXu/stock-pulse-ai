# Watchlist AI Scores

Watchlist scoring uses Route A: it aggregates stored analysis and decision signals and never starts a new LLM call. A symbol without a valid sentiment score returns `unanalyzed` with `score=null`; zero is never fabricated.

## Formula and sources

The current version is `watchlist_score_v1`. Sentiment alone supplies its 0–100 value. When a valid signal from the same analysis report exists, the composite is `0.75 × sentiment + 0.25 × signal`, rounded to an integer. Action hints are `strong_buy=90`, `buy=75`, `hold=50`, `watch=45`, `sell=25`, and `strong_sell=10`. When confidence is present, it shrinks the action hint toward neutral 50.

Sentiment must be finite and within 0–100; confidence must be finite and within 0–1. Invalid inputs do not participate and are exposed through `degraded_reasons` and the factor `reason`.

## Signal lifecycle and coherence

The service reuses `DecisionSignalRepository` expiration and also excludes `expires_at <= now` at read time. Version 1 accepts only an active `source_type=analysis` signal whose `source_report_id` equals the latest analysis id. Older reports, manual signals, unknown actions, inactive signals, and expired signals cannot alter the score. Every factor carries its source id, report id, profile, independent `as_of`/`expires_at`, and formula version.

## Query and request bounds

`POST /api/v1/watchlist/scores` accepts at most 200 valid, unique market identities. Overflow, blanks, invalid formats, duplicate aliases, and unknown sort modes return a 4xx instead of truncating. Analysis and signals each use one database window query and return the stable `(created_at DESC, id DESC)` top row per canonical market identity; each `source_rows` value is therefore bounded by the number requested.

Identity uses `resolve_daily_stock_identity()`. It covers A-share exchange forms, Hong Kong `00700`/`HK00700`/`00700.HK`, U.S. bare and `.US` forms, and Japanese, Korean, and Taiwan suffixes while filtering cross-market numeric collisions.

## Time and freshness

Legacy `AnalysisHistory.created_at` values are server-local naive times and are converted to UTC at the analysis boundary. Naive `DecisionSignalRecord` values are UTC. The API emits only timezone-aware RFC3339 timestamps. Future clock skew clamps age to zero; `freshness` is a stable enum and `age_days` carries the exact day bucket.

## Web and integration boundary

`WatchlistScoreColumn` localizes factor keys and params in the Web layer; the backend sends no English presentation labels. Default sorting remains `manual`. `score_desc` and `score_asc` are non-destructive views and never overwrite T23 manual/drag order. The #963 integration contract is to pass the matching `WatchlistScoreItem` as the independent component's `item` prop; this PR does not edit `HomeStockWorkspace.tsx`.

## Failure, risk, and rollback

Aggregation failures use a stable internal error and never disclose exception text. Scores are lagging derived assistance, not investment advice. Rollback is a code revert of the endpoint, component, and generated types; there is no migration or persisted score data. If a later consumer is wired, revert its imports and API calls at the same time.

See [watchlist-ai-score.md](watchlist-ai-score.md) for Chinese.
