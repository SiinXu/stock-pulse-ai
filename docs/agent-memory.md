# Principal-scoped Agent memory projection foundation

**Status**: pure foundation referencing [#250](https://github.com/SiinXu/stock-pulse-ai/issues/250) and [#198](https://github.com/SiinXu/stock-pulse-ai/issues/198)

**Chinese**: [agent-memory_CN.md](agent-memory_CN.md)

The three `src/agent/memory_*` modules project records already authorized by a caller. They do not read storage, infer ownership, persist/cache derivatives, or inject production prompts. Existing `AgentMemory` and `BaseAgent` behavior is unchanged.

## Contract

- Every record has a `principal_id`; cross-principal rows, duplicate ids, and legacy unowned rows are rejected.
- Input is capped at 200; output limits are positive and capped at 3.
- Signals are canonical; numeric values are finite/ranged; outcome id, 5/20-day horizon, evaluation time, and correctness are all-or-none. `outcome_id` and `analysis_history_id` must be bounded positive integers and `was_correct` must be a real boolean, so invalid provenance fails at construction instead of crashing retrieval.
- Every timestamp (`observed_at`, `expires_at`, `evaluated_at`, `as_of`) must be a canonical UTC `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` instant inside `[2000, 2100)`, and is compared as a parsed instant. Malformed values such as `2026-8-01T00:00:00Z` are rejected rather than winning a lexicographic comparison against a canonical value.
- Projection is point-in-time against `as_of`: records observed after `as_of` are excluded, records already expired at `as_of` are excluded, and an evaluation dated after `as_of` is withheld from the episodic entry (`outcome_pending_as_of=true`) and cannot become evidence. A 2099 panel is empty at a 2026 `as_of`.
- Wrong/unevaluated predictions are observations only. Semantic evidence uses only provenance-linked correct outcomes, and each pattern owns exactly one `horizon_days`. One correct 5-day plus two correct 20-day results are two insufficient patterns, never one `sufficient_evidence` pattern.
- Projection contains typed facts and source ids, never stored model prose. Every string that can reach the payload — `principal_id`, `stock_code`, timestamps, signals, derived `pattern_id`/`source` — is restricted to a fixed alphabet, so stored free-form text cannot enter the boundary at all. It serializes as bounded strict JSON inside `NON_AUTHORITATIVE_MEMORY_DATA`.
- Optional vector ranking is explicit, not config-owned; CJK unigrams/bigrams provide coarse ranking. `vector_used` covers either layer.

## Remaining scope

Production use still requires authoritative principal assignment and legacy migration; per-user/layer consent; view/export/correct/delete/clear; retention; derived deletion/cache invalidation; run audit; and owned storage queries. Both issues remain open.

## Rollback

Revert the additive modules, tests, docs, and changelog line. There is no runtime hook, config, migration, or persisted derivative.
