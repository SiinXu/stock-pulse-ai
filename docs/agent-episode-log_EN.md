# Agent Evolution Episode Log

**Status**: foundation for issues [#1090](https://github.com/SiinXu/stock-pulse-ai/issues/1090) and prediction closed-loop epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107)

**Chinese**: [agent-episode-log.md](agent-episode-log.md)

## Purpose

Persist compact, queryable **episodes** after agent runs so offline eval, post-mortem, and weight calibration can replay trajectories without storing secrets.

| Field | Notes |
| --- | --- |
| `run_id`, `mode`, `symbol`, timestamps | Correlation keys |
| `trajectory_summary` | Tool names, success flags, optional argument fingerprints — not raw prompts |
| `lessons` | Typed reflection / post-mortem lessons |
| `outcome_labels` | Optional feedback / forward-return / prediction outcome labels |
| `soul_version` / `soul_hash` | Identity only — **never** full Soul charter text |

## Modules

| Path | Role |
| --- | --- |
| `src/schemas/agent_episode.py` | Strict contracts |
| `src/repositories/agent_episode_repo.py` | Append / query / retention |
| `src/services/agent_episode_service.py` | Feature flag, redaction, fail-soft writer |
| `src/migrations/versions/v202608120002_agent_episode_schema.py` | Table + append-only trigger |

## Configuration

| Env | Default | Behavior |
| --- | --- | --- |
| `AGENT_EPISODE_LOG_ENABLED` | `false` | Master switch |
| `AGENT_EPISODE_RETENTION_DAYS` | `90` | Age-based purge |
| `AGENT_EPISODE_MAX_ROWS` | `50000` | Capacity bound (oldest first) |

When disabled or when persistence fails, analysis continues. Episode writes never raise into the user-facing path.

## Runtime hook

`AgentExecutor.run` records an episode in a `finally` block via `try_record_agent_episode_from_result` when the flag is on.

## Retention

Documented hooks: `apply_retention(cutoff)` and `apply_capacity(max_rows)`. Invoked best-effort after successful appends.

## Rollback

Revert migration/modules/config/docs and the executor finally hook. Default-off means no production writes until enabled.
