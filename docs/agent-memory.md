# Principal-scoped Agent memory projection foundation

**Status**: pure foundation referencing [#250](https://github.com/SiinXu/stock-pulse-ai/issues/250) and [#198](https://github.com/SiinXu/stock-pulse-ai/issues/198)

**Chinese**: [agent-memory_CN.md](agent-memory_CN.md)

The three `src/agent/memory_*` modules project records already authorized by a caller. They do not read storage, infer ownership, persist/cache derivatives, or inject production prompts. Existing `AgentMemory` and `BaseAgent` behavior is unchanged.

## Contract

- Every record has a `principal_id`; cross-principal rows, duplicate ids, and legacy unowned rows are rejected.
- Input is capped at 200; output limits are positive and capped at 3; expired records are excluded.
- Signals are canonical; numeric values are finite/ranged; outcome id, 5/20-day horizon, evaluation time, and correctness are all-or-none.
- Wrong/unevaluated predictions are observations only. Semantic evidence uses only provenance-linked correct outcomes.
- Projection contains typed facts and source ids, never stored model prose, and serializes as bounded strict JSON inside `NON_AUTHORITATIVE_MEMORY_DATA`.
- Optional vector ranking is explicit, not config-owned; CJK unigrams/bigrams provide coarse ranking. `vector_used` covers either layer.

## Remaining scope

Production use still requires authoritative principal assignment and legacy migration; per-user/layer consent; view/export/correct/delete/clear; retention; derived deletion/cache invalidation; run audit; and owned storage queries. Both issues remain open.

## Rollback

Revert the additive modules, tests, docs, and changelog line. There is no runtime hook, config, migration, or persisted derivative.
