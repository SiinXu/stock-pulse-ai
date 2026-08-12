# Analysis Stage Checkpoint & Reproducibility

中文：[analysis-checkpoint-resume.md](./analysis-checkpoint-resume.md)

## Background

Long multi-agent analyses waste tokens when a process interrupt forces a full rerun. The task queue already requeues in-flight `stock_analysis` work after restart, and daily-bar fetch already resumes by trading day. This feature adds **analysis stage-level** checkpoints and reproducibility controls on top of those paths.

Related issues: #121, #136.

## Layers

| Layer | Status | Behavior |
| --- | --- | --- |
| Task queue | Existing | Safe requeue of `stock_analysis` after process restart; same `task_id` is used as `query_id` |
| Market fetch | Existing | Skip fetch when required bars for the target trading day already exist |
| **Analysis stages** | **New** | Persist multi-agent stage outputs; exact-replay resume when the compatibility fingerprint matches |
| **Reproducibility** | **New** | Record a run-configuration snapshot; optionally pin seed / temperature |

## Consistency contract

Resume must not silently change conclusions:

1. Completed stages are reused only when `compatibility_fingerprint` matches exactly (exact-replay).
2. Any change to models, temperature, pipeline/persona/skills, key feature flags, report type, or analysis phase invalidates the checkpoint and forces a full rerun.
3. Missing or corrupt stage payloads invalidate the checkpoint.
4. `force_full` / API `force_refresh` / `ANALYSIS_CHECKPOINT_FORCE_FULL=true` bypasses checkpoints.
5. Report `context_snapshot` records `analysis_checkpoint` and `run_configuration`, including resume and consistency labels.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANALYSIS_CHECKPOINT_ENABLED` | `true` | Master switch for stage checkpoints |
| `ANALYSIS_CHECKPOINT_DIR` | `./data/checkpoints` | Checkpoint directory |
| `ANALYSIS_CHECKPOINT_TTL_HOURS` | `24` | TTL cleanup in hours (`0` disables) |
| `ANALYSIS_CHECKPOINT_FORCE_FULL` | `false` | Force a full rerun |
| `REPRO_MODE_ENABLED` | `false` | Prefer deterministic local seed + temperature=0 |
| `REPRO_RECORD_CONFIG` | `true` | Always record the run-configuration snapshot |
| `REPRO_SEED` | empty / 0 | Seed used when repro mode is enabled |

API `force_refresh=true` also bypasses stage checkpoints.

## Limitations

- Provider-side sampling may remain non-deterministic even at temperature 0.
- Live market data and search results can change between a full run and a later attempt; exact-replay reuses **stored agent stage outputs** and does not re-call the LLM for completed stages.
- Checkpoints are process-local filesystem state, not a distributed queue (ADR-004 / ADR-008).

## Implementation entry points

- `src/services/analysis_stage_checkpoint.py`
- Wiring: `src/core/stages/orchestration.py`, `src/agent/orchestrator_parts/pipeline.py`
- Metadata: `context_snapshot.analysis_checkpoint` / `context_snapshot.run_configuration`
