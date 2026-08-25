# Agent promotion checklist (dry-run CLI)

**Issue:** [#1093](https://github.com/SiinXu/stock-pulse-ai/issues/1093) first slice
**Chinese:** [agent-promotion_CN.md](agent-promotion_CN.md)

This document is the operator checklist for the **opt-in dry-run promotion CLI**.
It does **not** activate experimental Skills, router rules, or production flags.
Governed Skill-pin activation in the live catalog remains a later #1093 leftover.

Invocation is the only gate. There is no config-registry key, scheduler, admin
HTTP, or `EVOLUTION_AUTO_PROMOTE_SKILLS` environment variable.

## Safety contract

| Rule | Enforcement |
| --- | --- |
| Experimental candidates stay in a sidecar JSON store | `AgentPromotionService` refuses `strategies/`, `src/agent/skills/`, plugin dirs, and eval fixtures as `--store-dir` |
| Production defaults stay off | Default SkillRouter IDs are unchanged when the CLI is unused |
| Receipts never auto-promote | Embedded `PromotionReceipt.auto_promote=false`; sandbox `auto_promote_to_production=false` |
| Approve is not activation | `approve` / `reject` flip sidecar `review_state` only |
| Soul / catalog bytes are immutable on this path | CLI never rewrites Agent Soul or `strategies/*.yaml` |
| Eval is offline | `score` reuses `prediction_eval_service` (and trajectory eval when a fixture includes a trajectory). It does not start a live agent run |

Rollback for this slice: leave the experimental id unactivated and revert any
Skill-id pin. There is no database Soul rewrite to undo. Revert the CLI, library,
tests, and these docs if the feature itself must be removed.

## Review checklist

Use this list before treating a sidecar `approved` row as ready for a **later**
governed activation PR (not performed here):

1. **Safety** — candidate lives only in the sidecar; no file under `strategies/` or `skills/experimental/`.
2. **Eval deltas** — `score` completed against the frozen fixture/episode lessons; failed checks are understood.
3. **Sample size** — this dry-run scores the source case. Do not treat a single fixture as production evidence.
4. **Receipt** — `review_required=true`, `auto_promote=false`, `first_live_run_guard=human_approval_required`.
5. **Rollback** — unactivated experimental id; revert Skill pin; no Soul rewrite.

`approved` on the sidecar is a review record. It is not a runtime flag.

## CLI

```bash
python scripts/agent_evolve.py propose --fixture tests/fixtures/prediction_eval/cases/pred-seeded-miss-lesson.json
python scripts/agent_evolve.py score --proposal-id promo-<hex>
python scripts/agent_evolve.py status
python scripts/agent_evolve.py approve --proposal-id promo-<hex>
python scripts/agent_evolve.py reject --proposal-id promo-<hex>
```

Optional `--store-dir` (default `artifacts/agent_evolve`). Optional propose
sources: `--case-id <prediction-eval-id>` or `--episodes <json>`. `--kind` is
`experimental_skill_id` (default) or `router_rule` and is stored on the sidecar
only.

## Persistence, errors, idempotency

- **Persistence:** one JSON file per proposal, atomic temp + `fsync` + replace, process lock.
- **Proposal id:** content hash of candidate kind + case id + canonical lessons. Re-proposing the same source returns the existing sidecar.
- **Missing proposal:** `score` / `status --proposal-id` / `approve` / `reject` fail closed and do not create a file.
- **Approve:** requires `review_state=scored`. Repeating approve is idempotent. Rejected proposals cannot be approved.
- **Corrupt / activating receipt:** `auto_promote=true` (or `review_required=false`) fails closed on mutating commands.
- **Write failure:** temp file is discarded; the previous sidecar bytes remain.

## Related

- [Prompt / Skill versioning](prompt-skill-versioning_EN.md) — identity and pins; this CLI consumes them without activating Skills
- [Agent sandbox](agent-sandbox.md) — `PromotionReceipt.auto_promote=false`
- [Prediction verification rollout](prediction-verification-rollout_EN.md) — auto-promote stays hard off
