# Error-pattern encyclopedia from lessons

**Status**: V1 library path for [Issue #1138](https://github.com/SiinXu/stock-pulse-ai/issues/1138)

**Chinese**: [agent-error-pattern-encyclopedia.md](agent-error-pattern-encyclopedia.md)

## Role in the evolution stack

| Layer | Owner | Role |
| --- | --- | --- |
| Lessons (input) | `#1089` / `#1103` / PR `#1196` | Typed `ReflectionLesson` per episode / resolved forecast |
| **Encyclopedia (aggregation)** | **`#1138` (this doc)** | Cluster lessons into human-editable pattern cards; inject top-K checklists |
| Soul charter | `src/agent/soul.py` | Immutable; never rewritten by lessons or patterns |

Lessons are **input**. The encyclopedia is the **aggregation layer**. Cards reference source episodes; they are not free-form diary prose and not Soul edits.

## Product rules

1. Cluster recurring lessons by typed kind into searchable cards.
2. Humans may edit title / description / triggers / remedy, or disable a card.
3. Every human edit (including disable/enable/re-judge) **leaves an append-only audit trail**.
4. Analysis-time retrieval injects only **enabled** cards, under **top-K** and **char budget** quotas.
5. Injection is a **read-only checklist** wrapped as untrusted data. It must not change Agent Soul charter bytes.
6. Default **off** (`AGENT_ERROR_PATTERN_ENABLED=false`).

## Card fields

| Field | Meaning |
| --- | --- |
| `pattern_id` | Stable id (`pattern:<kind>`) |
| `kind` | Shared lesson kind (`evidence_gap`, `overconfidence`, `horizon_mismatch`, …) |
| `title` / `description` | Human-readable card text (seeded, overridable) |
| `triggers` | When this pattern tends to appear |
| `remedy` | Bounded next-time hint (not a Soul rewrite) |
| `stats` | `occurrence_count`, severity counts, `last_seen_at`, `episode_refs` |
| `enabled` | Disabled cards are never injected |
| `revision` | Bumps on cluster merge and human edit |
| `human_locked_fields` | Fields a human edited; reclustering preserves them |

### Kind mapping (product language)

| Kind | Product framing |
| --- | --- |
| `evidence_gap` | Data / evidence defect |
| `overconfidence` | Overconfidence |
| `horizon_mismatch` | Timing misjudgment |
| `regime_shift` | Regime / phase misread |
| `tool_failure` | Tool/source failure treated as inventable data |
| `risk_omission` | Risk / invalidation omission |
| `overclaim` | Prose treated as checkable claim |
| `format_violation` | Schema / format violation |
| `other` | Typed residual |

## Modules

| Module | Role |
| --- | --- |
| `src/agent/evolution/lessons.py` | Shared lesson taxonomy (input contract; shared with #1196) |
| `src/agent/evolution/error_patterns.py` | Cards, clustering, store, human edit audit, retrieval |
| `src/agent/evolution/guards.py` | Soul identity snapshot / assert |

## API surface (library)

```python
from src.agent.evolution import (
    ErrorPatternEncyclopedia,
    inject_error_pattern_checklist,
    retrieve_error_patterns,
)

store = ErrorPatternEncyclopedia()
store.ingest_lessons(episode_lesson_bundles)   # cluster / merge
store.human_edit("pattern:overconfidence", actor="analyst:a", title="...", remedy="...")
store.disable("pattern:overconfidence", actor="analyst:a", note="noisy")

result = retrieve_error_patterns(store, top_k=3, char_budget=2000)
# result.rendered_checklist  — non-authoritative block for prompt assembly
# result.cards               — enabled cards only; disabled excluded
```

Human edit audit: `store.list_edit_events(pattern_id=...)`.

Optional snapshot: `export_snapshot()` / `import_snapshot()` (V1 has no DB migration).

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_ERROR_PATTERN_ENABLED` | `false` | Master switch for analysis injection |
| `AGENT_ERROR_PATTERN_INJECT_TOP_K` | `3` | Max cards injected (hard cap 3) |
| `AGENT_ERROR_PATTERN_INJECT_CHAR_BUDGET` | `2000` | Max checklist characters (hard cap 8000) |

## Acceptance mapping

| Criterion | Coverage |
| --- | --- |
| Cards retrievable | `retrieve_error_patterns` / `list_cards` |
| Disabled cards not injected | `enabled=false` excluded from analysis path |
| Injection does not change Soul charter bytes | Soul snapshot + charter byte assert in retrieval tests |
| Pattern refs back to episodes | `stats.episode_refs` |
| Human edit leaves audit trail | `PatternEditEvent` append-only log |
| Quota | top-K + char budget |

## Out of scope (V1)

- Production Orchestrator auto-wire (library path; default off)
- Durable multi-tenant DB tables / Web UI for card editing
- Full post-mortem / reflection loop (owned by #1196 / #1103 / #1089)

## Rollback

Set `AGENT_ERROR_PATTERN_ENABLED=false` or revert this change. No DB migration.

## Related

- Lessons input: `docs/agent-reflection-postmortem_EN.md` (when #1196 lands)
- Layered memory (different layer): `docs/agent-memory.md`
- Soul charter: `docs/agent-soul.md`
