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
| `outcome_labels` | Optional feedback / forward-return / prediction outcome labels. Issue #1105 user feedback is **not** written here. |
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

When disabled, the executor does not import the episode writer or initialize its repository. When enabled, module loading, database initialization, validation, append, and retention failures are isolated from both successful Agent results and original Agent exceptions. Episode writes never raise into the user-facing path.

## Runtime hook

`AgentExecutor.run` records an episode in a guarded `finally` block via `try_record_agent_episode_from_result` only when the flag is on. An injected `context.run_id` (or `task_id`) is preferred over a generated identifier so episodes remain correlated with their originating run.

## Retention

Documented hooks: `apply_retention(cutoff)` and `apply_capacity(max_rows)`. Invoked best-effort after successful appends.

Queries and replay lists are bounded to 200 rows/IDs. Persisted JSON corruption is surfaced as `agent_episode_corrupt_json`; it is never converted into an apparently valid empty trajectory or lesson list.

## Optional user feedback (#1105)

Authenticated `PUT`/`GET` APIs store run (`useful|partial|wrong|harmful`) and prediction (`agree_hit|agree_miss|disagree_score|context_note`) opinion in sidecar tables. They do **not** `UPDATE` append-only `agent_episodes`. Consumers that want a merged view must join at read time. Absence of feedback does not block automatic prediction resolve or evolution.

## Rollback

Revert migration/modules/config/docs and the executor finally hook. Default-off means no production writes until enabled.
