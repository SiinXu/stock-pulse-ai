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
- Trajectory / optional immediate LLM calls also charge `ctx.meta["mode_budget_account"]` when the run has one. They do **not** go through `run_agent_loop`, so they are counted once. Cross-run meta-review stays offline and has no run account.

## Three layers

| Layer | Trigger | Budget (default) | Output |
| --- | --- | --- | --- |
| **Immediate** (in-loop step critique) | Tool failure or contradictory observation during plan→act→observe | Deterministic in production | Typed lessons + standardized `replan_reason_kinds` |
| **Trajectory** (end-of-run) | Config-enabled end-of-run reflection | `AGENT_REFLECTION_LLM_BUDGET` (**0–64**, default **1**) | Full `ReflectionResult` on run meta |
| **Meta** (cross-run offline job) | Offline CLI/job when sample count ≥ threshold | Deterministic | Markdown/JSON evolution report with recommended actions |

Shared taxonomy (`LESSON_KINDS`):

`evidence_gap`, `overclaim`, `overconfidence`, `tool_failure`, `risk_omission`,
`format_violation`, `regime_shift`, `horizon_mismatch`, `other`.

## Episode storage

Typed lessons project into the episode lesson shape used by the evolution
episode log (`kind` / `severity` / `claim_ref` / `remedy` / `source_step`).
See `src/agent/evolution/episode_lessons.py`.

- In-memory sink: offline tests / meta-review fixtures.
- Production planning path (`run_with_planning`) harvests step-critique artifacts
  into `planning_metadata` and, when `AGENT_REFLECTION_ENABLED`, runs trajectory
  reflection at end-of-run (success or plan failure).
- Episode persistence remains owned by the single end-of-run finalizer from
  #1210. This change does not create or soft-append a second episode. Until that
  integration lands, reflection output remains available in `planning_metadata`.

The trajectory layer calls the executor's configured provider with bounded,
redacted run success, tool trajectory, and planning outcome evidence. Provider
failure is recorded as `status=error` / `validation_status=error`; it never
fabricates a successful reflection or a new lesson. Deterministic immediate
lessons, when present, are preserved as evidence.

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
Input is capped at 50,000 unique episodes and 16 MiB for the CLI JSON file.
Malformed or duplicate episode records fail the job instead of being filtered.
Counts and tie ordering are deterministic, and report basenames reject path
traversal. Markdown and JSON artifacts are replaced atomically per file.

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
| `AGENT_REFLECTION_ENABLED` | `false` | Enable trajectory reflection |
| `AGENT_REFLECTION_LLM_BUDGET` | `1` | Max provider calls per trajectory loop (`0`–`64`; shared with run-local reflection) |
| `AGENT_META_REVIEW_ENABLED` | `false` | Enable offline meta-review path |
| `AGENT_META_REVIEW_MIN_EPISODES` | `30` | Sample threshold (`1`–`50000`) |

Encyclopedia run-local keys remain in force: `AGENT_REFLECTION_MAX_REVISE` (default 1)
and `AGENT_REFLECTION_LLM_BUDGET` is shared (hard max 64). Immediate and meta LLM
budgets stay code constants defaulting to 0.

Library callers can still inject an explicit `LlmCallBudget` and callback into
the immediate/meta functions for bounded experiments. Those are not runtime
configuration capabilities and are not used by the production paths above.

## Dependency note

This package reuses the #1196 lesson structure (`ReflectionLesson` /
`ReflectionResult` / `LESSON_KINDS`). Episode persistence integration remains
dependent on #1210's single end-of-run finalizer; this PR deliberately does not
add a competing writer.

## Rollback

Set enable flags to `false` or remove them. No DB migration in this change.
