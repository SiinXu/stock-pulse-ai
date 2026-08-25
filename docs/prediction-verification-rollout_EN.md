# Prediction verification loop — safe rollout

> 中文：[prediction-verification-rollout.md](prediction-verification-rollout.md)

Operator-facing rollout for the landed verification / post-mortem flags (Issue [#1115](https://github.com/SiinXu/stock-pulse-ai/issues/1115), Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107)).

This page documents **defaults and a safe enable order**. It does **not** close every #1115 acceptance item (see [Remaining issue gaps](#remaining-issue-gaps)).

Research / quality-ops only. Not a returns-guarantee product surface.

## Safe rollout sequence

Use this order. Do not skip ahead to adapters or promotion.

1. **All flags off.** Ship and run with landed defaults: extraction off, resolver scheduler off, postmortem off, online adapters off. Analysis, history save, and notifications stay on their existing paths.
2. **Enable extraction and verify analysis remains healthy.** Set `PREDICTION_EXTRACT_ENABLED=true`. Run a normal analysis / Agent finalize. Extraction exceptions are logged and **never** fail analysis or history save. Inspect attached drafts / `agent_predictions` pending rows only after that health check.
3. **Enable the resolver on exactly one scheduled worker, or invoke the cron CLI explicitly.** Either:
   - set `PREDICTION_RESOLVE_ENABLED=true` on **one** process that already runs the existing scheduler (`python main.py --schedule`, or API/Web/Desktop serve that registers `RuntimeSchedulerService`), background task name `prediction_resolver`; **or**
   - keep `PREDICTION_RESOLVE_ENABLED=false` on app workers and run `python -m src.services.prediction_resolver` (optional `--limit`, `--worker-id`, `--json`).
   Manual CLI invocation is an **intentional operator gate**: the CLI runs one `tick()` even when the scheduler flag is off. Do not register the background worker on every app replica.
4. **Enable miss/partial-only postmortem with skip-clean-hits.** Set `AGENT_POSTMORTEM_ENABLED=true` and leave `AGENT_POSTMORTEM_SKIP_CLEAN_HITS=true` (default). Hits are not enqueued. Drain happens after a non-overlap resolver tick, capped by `PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK` (default `10`).
5. **Enable gated adapters only after the sample threshold.** Set `AGENT_ONLINE_ADAPTERS_ENABLED=true` only once `AgentMemory` / resolved-forecast samples can meet `AGENT_ONLINE_ADAPTERS_MIN_SAMPLES` (default `30`). Below the threshold, adapters stay identity (`applied=false`, `reason=insufficient_samples`).
6. **Auto-promote stays hard off.** There is no env key that turns skill auto-promotion on. Sandbox `PromotionReceipt.auto_promote` is hardcoded `false` until an eval gate exists.

To stop **new** verification work without breaking analysis: set the enable flags back to `false` (or omit them). Pending `agent_predictions` rows are left in place; the analysis path does not depend on them.

## Issue example names are not aliases

Issue #1115 lists example names (`e.g.`). Those strings are **not** registered config keys and **must not** be treated as aliases, fallbacks, or env synonyms of the landed keys. Setting an example name in `.env` has no effect.

| Issue #1115 example | Landed key or surface | Landed default | Notes |
| --- | --- | --- | --- |
| `PREDICTION_VERIFY_ENABLED` | `PREDICTION_EXTRACT_ENABLED` **and** `PREDICTION_RESOLVE_ENABLED` | both `false` | Verification is two flags. The example name is not a parent alias. |
| `PREDICTION_RESOLVER_INTERVAL_SEC` | `PREDICTION_RESOLVE_INTERVAL_SECONDS` | `60` (scheduler floor `30`) | Different spelling; not an alias. |
| `PREDICTION_RESOLVER_BATCH_LIMIT` | `PREDICTION_RESOLVE_MAX_PER_TICK` | `50` | Different spelling; not an alias. |
| `PREDICTION_FETCH_CONCURRENCY` | `PREDICTION_RESOLVE_FETCH_CONCURRENCY` | `4` | Different spelling; not an alias. |
| `PREDICTION_POSTMORTEM_ENABLED` | `AGENT_POSTMORTEM_ENABLED` | `false` | Different prefix; not an alias. |
| `PREDICTION_POSTMORTEM_ON_HIT` | `AGENT_POSTMORTEM_SKIP_CLEAN_HITS` | `true` | **Inverted** vs an “on-hit” switch. Default skips clean hits. Hits are not enqueued. |
| `PREDICTION_POSTMORTEM_CONCURRENCY` | *(none)* | hardcoded `2` | Drain workers are code-local (`_DEFAULT_DRAIN_WORKERS`). No env key. |
| `PREDICTION_POSTMORTEM_MAX_PER_TICK` | `PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK` | `10` | Different prefix; not an alias. |
| `PREDICTION_FLAT_EPSILON_PCT` | `ClaimScoreConfig.sideways_epsilon` (`flat_epsilon` constructor alias) | `0.001` (0.1%) | Scorer-local / non-env. No `PREDICTION_FLAT_EPSILON_PCT` registry key. |
| `EVOLUTION_MIN_SAMPLES` | `AGENT_ONLINE_ADAPTERS_MIN_SAMPLES` | `30` | Different spelling; not an alias. |
| `EVOLUTION_AUTO_PROMOTE_SKILLS` | *(none)* | hardcoded `false` | `PromotionReceipt.auto_promote` and sandbox `auto_promote_to_production` stay false. No env key. |

Landed keys resolve through the existing `Config` / config-registry path. Example names do not.

## Current deferrals and boundaries

These are **current product facts**, not operator-tunable rollout knobs:

| Boundary | Current behavior |
| --- | --- |
| Postmortem concurrency | Hardcoded `2` in `drain_postmortem_queue` (`_DEFAULT_DRAIN_WORKERS`). Scheduler and CLI do not pass `max_workers`. There is no `PREDICTION_POSTMORTEM_CONCURRENCY` env. |
| Flat epsilon | Scorer-local on `ClaimScoreConfig` (`sideways_epsilon`, optional constructor alias `flat_epsilon`). Not an environment variable. |
| Auto-promote | Hard `false` on `PromotionReceipt` and sandbox policy until an eval gate exists. Do not invent `EVOLUTION_AUTO_PROMOTE_SKILLS=true`. |
| Manual resolver CLI | `python -m src.services.prediction_resolver` is an intentional operator gate. It loads config for caps (lease, batch, fetch concurrency, circuit, postmortem budget) and runs one tick **even when** `PREDICTION_RESOLVE_ENABLED` is false. The scheduler flag only registers the background worker. |
| Scheduler vs CLI postmortem inject | Queue inject follows `AGENT_POSTMORTEM_ENABLED` only. A **scheduled** drain also needs the resolver worker (`PREDICTION_RESOLVE_ENABLED`). CLI drain does not require that scheduler flag. |
| Disabling flags | Extraction off → hooks are no-ops. Resolver scheduler off → no `prediction_resolver` background task (CLI still available). Postmortem off → no queue inject / drain. Adapters off → identity. Analysis continues in all cases. |

## Related docs

- [Prediction Extraction](prediction-extraction_EN.md)
- [Prediction Horizon Resolver](prediction-resolver_EN.md)
- [Agent Reflection and Forecast Post-mortem](agent-reflection-postmortem_EN.md)
- [Deterministic Prediction Claim Scorer](prediction-claim-scorer_EN.md)
- [Principal-scoped layered Agent memory](agent-memory.md) (gated adapters)
- [Agent / Strategy Simulation Sandbox](agent-sandbox.md) (hard `auto_promote=false`)
- Env inventory: [environment-variables_EN.md](environment-variables_EN.md)

## Remaining issue gaps

Issue #1115 acceptance is **not** fully closed by this documentation slice:

- Documented defaults and this safe rollout order — this page.
- Flags readable from a single config resolve path — **landed keys only**. Example names stay unregistered on purpose.
- Disabling flags stops new work without breaking analysis — true for the landed enable flags as documented above; operators must use those keys, not the issue examples.
- Env-tunable postmortem concurrency, env-tunable flat epsilon, and auto-promote after an eval gate remain **deferred**.
