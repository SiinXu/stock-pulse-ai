# Agent 演化 Episode 日志

**状态**：Issue [#1090](https://github.com/SiinXu/stock-pulse-ai/issues/1090) 与预测闭环 Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107) 基础能力

**English**: [agent-episode-log_EN.md](agent-episode-log_EN.md)

## 目的

在 Agent 运行结束后持久化紧凑、可查询的 **episode**，供离线评测、复盘与权重校准重放轨迹；默认不存储密钥、原始 provider 载荷或完整 Soul 章程正文。

关闭功能时不会导入写入器或初始化仓库；开启后，模块加载、数据库初始化、写入与清理失败均不得覆盖 Agent 的成功结果或原始异常。查询与重放输入上限为 200 条，持久化 JSON 损坏会显式报错，绝不伪装成空轨迹。

Issue #1105 的可选用户反馈写入 sidecar（`agent_run_feedback` / `agent_prediction_feedback`），通过读时 join 与 episode 合并；不会 `UPDATE` append-only 的 `agent_episodes`，也不会改写 resolver actuals。无反馈时自动核验与进化仍继续。

Issue #1096 第一片的研究用前向收益分桶（`1d_up` / `1d_down` / `1d_flat` / `5d_up` / `5d_down` / `5d_flat`）写入 sidecar `agent_episode_forward_returns`，按已有 `episode_id` + horizon 做 upsert，并复制 `run_id`。这些标签只用于模型运维质量，不是投资建议，也不承诺交易 alpha。入口是显式 CLI：`python scripts/label_forward_returns.py --as-of YYYY-MM-DD`（可选 `--horizon`、`--run-id`、`--dry-run`）。没有配置注册表键，也没有调度器。价格只走现有 ActualsFetcher / `DataFetcherManager` 路径，绝不编造；缺 bar、日历无法计算窗口、或 episode 没有 symbol 时跳过该行。未知 bucket 会被拒绝。不写 `prediction_outcome`，也不 `UPDATE` `agent_episodes`。缺失标签保持缺席，校准与进化保持中性。

Issue #1096 评测 fixture 的策展等级语义槽仍是 `EpisodeOutcomeLabels.manual_grade`，但 **episode 行本身不收紧该字段**：历史 append-time 值（例如 `wrong`）读回仍合法。后置写入只走 sidecar `agent_episode_curator_grades`（按 `episode_id` upsert，复制 episode 的 `run_id`），允许值为 `pass` / `fail` / `partial` / `harmful`，不得 `UPDATE` `agent_episodes`。入口是显式 CLI：`python scripts/label_curator_grades.py --fixture path.json`（可选 `--episode-id`、`--dry-run`）。没有配置注册表键，也没有调度器。缺失或空白 fixture `manual_grade` 视为缺席，不写中性占位；CLI/sidecar 未知 token 会 fail-closed 且不落库。适配器消费仍属 #1106。

追加成功后的遗忘是按标的的：只删除本次写入 symbol 上、严格早于 cutoff 的行，以及超出按标的行数上限的最旧行。无 symbol 不删除。无 cutoff 且无 max_rows 是无策略，保留数据，并且 `remaining_count` 必须是实时 COUNT。不可逆 DELETE 会在同一事务里先写入一条仅元数据的 EvolutionEvent，再按 SQLite bind 上限分块 `DELETE ... id IN (...)`（为 `symbol` 预留一个 bind）；分块不是多次提交，审计失败则整笔回滚。代码回滚不能恢复已删行，只能靠备份 / PITR。无作用域的 `apply_retention` / `apply_capacity` fail-closed。仓库层事务失败会抛出并回滚；分析路径仍 fail-soft。配置、模块与回滚说明见英文版（与实现保持一致）。
