# Multi-level Reflection (Immediate / Trajectory / Meta-review)

Issue **#1094** under Epic **#1107**. Builds on the typed lesson taxonomy from
the prediction post-mortem / reflection track (**#1196**, kinds in
`src/agent/evolution/lessons.py`).

## Product rules (Epic #1107)

- Research / quality-ops framing only — not a guaranteed-returns product.
- **No runtime mutation** of Agent Soul charter/version/hash.
- **No runtime mutation** of ToolSurface denials / allow boundaries.
- Non-parseable prose does **not** become a fake verifiable claim or new lesson kind.
- All optional LLM work is **budgeted**; exhaustion is explicit (`budget_skipped`), never silent success.

## Three layers

| Layer | Trigger | Budget (default) | Output |
| --- | --- | --- | --- |
| **Immediate** (in-loop step critique) | Tool failure or contradictory observation during plan→act→observe | `AGENT_STEP_CRITIQUE_LLM_BUDGET` (default **0** = deterministic) | Typed lessons + standardized `replan_reason_kinds` |
| **Trajectory** (end-of-run) | Config-enabled end-of-run reflection | `AGENT_REFLECTION_LLM_BUDGET` (default **1**) | Full `ReflectionResult` on run meta |
| **Meta** (cross-run offline job) | Offline CLI/job when sample count ≥ threshold | `AGENT_META_REVIEW_LLM_BUDGET` (default **0**) | Markdown/JSON evolution report with recommended actions |

Shared taxonomy (`LESSON_KINDS`):

`evidence_gap`, `overclaim`, `overconfidence`, `tool_failure`, `risk_omission`,
`format_violation`, `regime_shift`, `horizon_mismatch`, `other`.

## Episode storage

Typed lessons project into the episode lesson shape used by the evolution
episode log (`kind` / `severity` / `claim_ref` / `remedy` / `source_step`).
See `src/agent/evolution/episode_lessons.py`. When the episode service
(#1090 / #1210) is present, the same dicts are appendable; otherwise an
in-memory sink supports offline tests and meta-review.

## Planning replan alignment

On observation-driven replan, the planning loop records
`replan_reason_kinds` from the shared taxonomy and, when step critique is
enabled, attaches `step_critique_result` for episode linkage.

The production AgentExecutor path (`src/agent/planning/product.py`) binds the
resolved Config onto `context["config"]` so `AGENT_STEP_CRITIQUE_ENABLED` is
honored on real runs (not only library callers that hand-build context).

## Meta-review sample threshold

`AGENT_META_REVIEW_MIN_EPISODES` (default **30**). Below the threshold the job
returns `status=threshold_not_met` and does **not** invent recommended actions.

Offline CLI:

```bash
python scripts/run_meta_review.py --episodes path/to/episodes.json --output-dir artifacts/meta_review --force
```

Report includes:

- Top failure kinds (counts + example `run_id`s)
- Worst tools
- Modes with high revise rate
- Recommended actions such as “promote skill X”, “investigate provider Y”, “tighten router for case Z”
- Explicit flags: `mutates_soul=false`, `mutates_tool_surface=false`, `mutates_runtime_config=false`

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_STEP_CRITIQUE_ENABLED` | `false` | Enable immediate step critique |
| `AGENT_STEP_CRITIQUE_LLM_BUDGET` | `0` | Optional LLM enrichment per critique |
| `AGENT_REFLECTION_ENABLED` | `false` | Enable trajectory reflection |
| `AGENT_REFLECTION_LLM_BUDGET` | `1` | Max LLM calls per trajectory loop |
| `AGENT_REFLECTION_MAX_REVISE` | `1` | Max in-run revise passes |
| `AGENT_META_REVIEW_ENABLED` | `false` | Enable offline meta-review path |
| `AGENT_META_REVIEW_MIN_EPISODES` | `30` | Sample threshold |
| `AGENT_META_REVIEW_LLM_BUDGET` | `0` | Optional LLM enrichment for meta report |

## Dependency note

Prediction verification layer (#1186–#1210) and typed post-mortem (#1196) were
**not merged** when this work landed. This package **reuses the #1196 lesson
structure** (`ReflectionLesson` / `ReflectionResult` / `LESSON_KINDS`) and the
episode lesson projection shape from #1210 so later merges can converge on the
same contracts.

## Rollback

Set enable flags to `false` or remove them. No DB migration in this change.
