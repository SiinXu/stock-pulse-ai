# Agent Memory Contract (Episodic + Semantic)

This document describes the layered agent memory system introduced for Issue #250.

## Goals

- Give specialised agents **relevant past context** without flattening all history into one bag of text.
- Keep memory **optional and fail-neutral** so default installs are unchanged.
- Support **optional vector re-ranking** without heavy dependencies (no faiss / chroma).

## Layers

| Layer | Status | Responsibility |
| --- | --- | --- |
| Short-term (working memory) | **Deferred / existing** | Single-run context lives in `AgentContext`, prefetched `ctx.data`, and the message list. Not reimplemented here. |
| Episodic | **Delivered** | Concrete past analyses for a stock, optionally linked to `AnalysisHistory.id`. |
| Semantic | **Delivered** | Cross-episode patterns (e.g. repeated signal bias) distilled from history. Low sample counts stay explicitly neutral. |
| Long-term preferences | **Deferred** | User risk tolerance / communication style profiles are out of scope for this release. |

## Feature flags

| Variable | Default | Effect |
| --- | --- | --- |
| `AGENT_MEMORY_ENABLED` | `false` | Master switch. When off, every public method returns empty / neutral values identical to the pre-layered API. |
| `AGENT_MEMORY_VECTOR_ENABLED` | `false` | Opt-in hashed bag-of-words re-ranking on top of structured results. When off or empty, retrieval is fully structured. |

Vector enablement is read from the environment (and from a future config attribute if present). It does not require WebUI registration to function.

## Public API (`src.agent.memory.AgentMemory`)

Backward-compatible methods (unchanged contracts):

- `get_stock_history(stock_code, limit=5)`
- `get_calibration(...)` / `calibrate_confidence(...)`
- `get_skill_performance` / `compute_skill_weights` (+ strategy aliases)

New layered methods:

- `retrieve_episodic(stock_code, limit=5, query=None) -> list[EpisodicMemoryEntry]`
- `retrieve_semantic(query=None, stock_code=None, limit=3) -> list[SemanticMemoryEntry]`
- `retrieve_layered(stock_code, query=None, ...) -> LayeredMemoryBundle`
- `format_prompt_context(stock_code, query=None, ...) -> str` — low-sensitivity prompt block

## Retrieval design

1. **Structured (default)**  
   Load recent `AnalysisHistory` rows via the existing storage facade.  
   - Episodic: map rows to entries; optional keyword score against `query`.  
   - Semantic: bucket by normalized signal; emit a pattern summary; mark `sufficient_evidence` only when evidence count ≥ 3.

2. **Vector (opt-in)**  
   Pure-Python feature hashing (dim 256, blake2b token hash) + cosine similarity.  
   Re-ranks structured candidates in-process. No new tables, no new package dependencies.

## Injection policy

`BaseAgent._build_memory_context` prefers `format_prompt_context` when it returns a real `str`, otherwise falls back to the legacy `get_stock_history` formatting (keeps existing mocks / tests working).

Injected text:

- Must not carry secrets, filesystem paths, or emails (see `sanitize_memory_text`).
- Is capped per summary fragment.
- Ends with an instruction to treat memory as context only.

## Neutral-when-insufficient

Aligned with `skill_opinion_weight_service`:

- Confidence calibration still requires `min_samples` (default 30).
- Semantic patterns with fewer than 3 supporting analyses are labeled insufficient and worded as neutral context, never as strong claims.

## Storage and rollback

- No new persistent memory tables in this release. Episodes are projections of `analysis_history`.
- Rollback = revert the PR. No data migration or drop script is required.
- If a future PR adds durable preference tables, ship a cleanup path with that change.

## Integration points (parallel batch)

- **T05 / T06**: `BaseAgent._build_memory_context` now calls `format_prompt_context` first. Planning / risk gates should not need to change memory injection.
- **Config registry (T12)**: optional WebUI registration of `AGENT_MEMORY_VECTOR_ENABLED` can be added later; runtime already honors the env flag.
- Do **not** modify `runner.py`, `executor.py`, `orchestrator.py`, or `risk_override.py` for memory work.
