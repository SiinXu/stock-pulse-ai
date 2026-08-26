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
| `outcome_labels` | Optional feedback / forward-return / curator-grade / prediction outcome labels stored on the episode row at append time. Issue #1105 user feedback, Issue #1096 forward-return buckets, and post-hoc #1096 curator grades are **not** written here. |
| `soul_version` / `soul_hash` | Identity only — **never** full Soul charter text |

## Modules

| Path | Role |
| --- | --- |
| `src/schemas/agent_episode.py` | Strict contracts |
| `src/repositories/agent_episode_repo.py` | Append / query / per-symbol forget |
| `src/services/agent_episode_service.py` | Feature flag, redaction, fail-soft writer |
| `src/migrations/versions/v202608120002_agent_episode_schema.py` | Table + append-only trigger |
| `src/repositories/agent_forward_return_repo.py` | Sidecar upsert for #1096 forward-return buckets |
| `src/services/forward_return_labeler.py` | CLI batch labeler (invocation is the gate) |
| `scripts/label_forward_returns.py` | Opt-in CLI entry |
| `src/migrations/versions/v202608250001_agent_forward_return_schema.py` | Sidecar table |
| `src/schemas/curator_grade.py` | Sidecar/CLI allowlist only; does not constrain episode rows |
| `src/repositories/agent_curator_grade_repo.py` | Sidecar upsert for #1096 eval-fixture curator grades |
| `src/services/curator_grade_ingester.py` | CLI fixture loader (invocation is the gate) |
| `scripts/label_curator_grades.py` | Opt-in CLI entry |
| `src/migrations/versions/v202608250002_agent_curator_grade_schema.py` | Sidecar table |

## Configuration

| Env | Default | Behavior |
| --- | --- | --- |
| `AGENT_EPISODE_LOG_ENABLED` | `false` | Master switch |
| `AGENT_EPISODE_RETENTION_DAYS` | `90` | Per-symbol age cutoff after a successful append for that symbol |
| `AGENT_EPISODE_MAX_ROWS` | `50000` | Per-symbol capacity after a successful append for that symbol (oldest first) |

When disabled, the executor does not import the episode writer or initialize its repository. When enabled, module loading, database initialization, validation, append, and retention failures are isolated from both successful Agent results and original Agent exceptions. Episode writes never raise into the user-facing path.

## Runtime hook

`AgentExecutor.run` records an episode in a guarded `finally` block via `try_record_agent_episode_from_result` only when the flag is on. An injected `context.run_id` (or `task_id`) is preferred over a generated identifier so episodes remain correlated with their originating run.

## Retention / forgetting (#1119 Slice 2)

Deterministic per-symbol forgetting is resolved by `src/schemas/memory_forget_policy.py` and applied by `AgentEpisodeRepository.apply_forget`. After a successful append, `AgentEpisodeService` forgets **only the stored symbol**, using existing `AGENT_EPISODE_RETENTION_DAYS` / `AGENT_EPISODE_MAX_ROWS` as per-symbol bounds (they are not table-wide caps) and the repository clock for cutoff. No symbol → no delete. `created_at < cutoff` is deleted; equality is kept. Capacity keeps the newest rows of that symbol. No-policy (neither cutoff nor max_rows) deletes nothing and still returns a live remaining COUNT. Irreversible DELETE inserts one metadata-only `episode.forget` EvolutionEvent in the same transaction before the delete, then issues chunked `DELETE ... id IN (...)` statements so each batch stays within SQLite `MAX_VARIABLE_NUMBER` (one bind reserved for `symbol`). Chunks do not commit separately; audit failure rolls back every chunk. Dry-run does not write an event. `append` commits before forget; insert+forget is not atomic. SQLite serializes writers; there is no `SELECT FOR UPDATE`. Unscoped `apply_retention` / `apply_capacity` fail closed and route through the same policy. Code revert cannot restore deleted rows — recovery requires backup / point-in-time restore. Analysis still fail-softs forget errors after append so episode failure cannot abort the Agent result.

Queries and replay lists are bounded to 200 rows/IDs. Persisted JSON corruption is surfaced as `agent_episode_corrupt_json`; it is never converted into an apparently valid empty trajectory or lesson list.

## Optional user feedback (#1105)

Authenticated `PUT`/`GET` APIs store run (`useful|partial|wrong|harmful`) and prediction (`agree_hit|agree_miss|disagree_score|context_note`) opinion in sidecar tables. They do **not** `UPDATE` append-only `agent_episodes`. Consumers that want a merged view must join at read time. Absence of feedback does not block automatic prediction resolve or evolution.

## Optional forward-return buckets (#1096)

Research-only 1d/5d direction buckets (`1d_up` / `1d_down` / `1d_flat` / `5d_up` / `5d_down` / `5d_flat`) live in the `agent_episode_forward_returns` sidecar, keyed by existing `episode_id` + horizon with `run_id` copied from the episode. They are **model-ops quality labels**, not trading advice and not a promised alpha signal.

Invocation is the only gate: run `python scripts/label_forward_returns.py --as-of YYYY-MM-DD` (optional `--horizon 1d` / `--horizon 5d`, `--run-id`, `--dry-run`). There is no config-registry key and no scheduler. The job reads daily history through the existing ActualsFetcher / `DataFetcherManager` path, never fabricates prices, and **skips** a row when the horizon bar is missing, the trading calendar cannot compute the window, or the episode has no symbol. Unknown bucket strings are rejected. The labeler does not write `prediction_outcome` and does not `UPDATE` `agent_episodes` (`trg_agent_episodes_immutable` stays in force). Missing labels stay absent; calibration and evolution continue with neutral behavior.

## Optional curator grades on eval fixtures (#1096)

`EpisodeOutcomeLabels.manual_grade` remains the optional semantic slot on the episode row and stays free-form (max 64). Historical append-time values such as `wrong` still read. Post-hoc eval-fixture ingest does **not** rewrite that field. It writes the `agent_episode_curator_grades` sidecar, keyed by `episode_id`, with `run_id` copied from the episode. Sidecar/CLI tokens are allowlisted as `pass` / `fail` / `partial` / `harmful` in `src/schemas/curator_grade.py`. The sidecar never `UPDATE`s append-only `agent_episodes` (`trg_agent_episodes_immutable` stays in force).

These grades are **model-ops quality labels** for eval fixtures, not trading advice and not a promised alpha signal.

Invocation is the only gate: run `python scripts/label_curator_grades.py --fixture path.json` (optional `--episode-id`, `--dry-run`). There is no config-registry key and no scheduler. The fixture is JSON: either `{"version":"curator_grade/1.0","grades":[...]}` or a bare array of grade objects. Each object needs `episode_id` and may include `run_id` and `manual_grade`. Missing or blank `manual_grade` is absence (no sidecar write, no fabricated neutral). Unknown tokens fail closed before any write. A fixture `run_id` that does not match the stored episode is rejected. Missing episodes are skipped. Adapter consumption of these labels is #1106.

## Rollback

Revert modules/config/docs/Settings help and the executor finally hook. Default-off means no production writes until enabled. Deleted episode rows cannot be restored from code; recovery requires backup / point-in-time restore.
