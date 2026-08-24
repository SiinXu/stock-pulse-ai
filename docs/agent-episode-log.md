# Agent 演化 Episode 日志

**状态**：Issue [#1090](https://github.com/SiinXu/stock-pulse-ai/issues/1090) 与预测闭环 Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107) 基础能力

**English**: [agent-episode-log_EN.md](agent-episode-log_EN.md)

## 目的

在 Agent 运行结束后持久化紧凑、可查询的 **episode**，供离线评测、复盘与权重校准重放轨迹；默认不存储密钥、原始 provider 载荷或完整 Soul 章程正文。

关闭功能时不会导入写入器或初始化仓库；开启后，模块加载、数据库初始化、写入与清理失败均不得覆盖 Agent 的成功结果或原始异常。查询与重放输入上限为 200 条，持久化 JSON 损坏会显式报错，绝不伪装成空轨迹。

Issue #1105 的可选用户反馈写入 sidecar（`agent_run_feedback` / `agent_prediction_feedback`），通过读时 join 与 episode 合并；不会 `UPDATE` append-only 的 `agent_episodes`，也不会改写 resolver actuals。无反馈时自动核验与进化仍继续。

Issue #1096 第一片的研究用前向收益分桶（`1d_up` / `1d_down` / `1d_flat` / `5d_up` / `5d_down` / `5d_flat`）写入 sidecar `agent_episode_forward_returns`，按已有 `episode_id` + horizon 做 upsert，并复制 `run_id`。这些标签只用于模型运维质量，不是投资建议，也不承诺交易 alpha。入口是显式 CLI：`python scripts/label_forward_returns.py --as-of YYYY-MM-DD`（可选 `--horizon`、`--run-id`、`--dry-run`）。没有配置注册表键，也没有调度器。价格只走现有 ActualsFetcher / `DataFetcherManager` 路径，绝不编造；缺 bar、日历无法计算窗口、或 episode 没有 symbol 时跳过该行。未知 bucket 会被拒绝。不写 `prediction_outcome`，也不 `UPDATE` `agent_episodes`。缺失标签保持缺席，校准与进化保持中性。

配置、模块与回滚说明见英文版（与实现保持一致）。
