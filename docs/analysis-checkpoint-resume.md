# Analysis Stage Checkpoint & Reproducibility

English: [analysis-checkpoint-resume_EN.md](./analysis-checkpoint-resume_EN.md)

## 背景

长运行多 Agent 分析（技术 / 情报 / 风险 / 决策等阶段）在中断后若全量重跑，会浪费 token 与时间。任务队列层已支持进程重启后的 in-flight **任务重排队**（`task_queue` checkpoint），数据层也有交易日断点续传；本能力在其之上增加 **分析阶段级** 检查点与可复现控制。

关联 Issue：#121、#136。

## 能力边界

| 层级 | 已有 / 新增 | 行为 |
| --- | --- | --- |
| 任务队列 | 已有 | 进程重启后 `stock_analysis` 安全 requeue；同一 `task_id` 作为 `query_id` |
| 行情拉取 | 已有 | 按目标交易日跳过已有 K 线 |
| **分析阶段** | **新增** | 多 Agent 阶段完成后落盘；兼容指纹匹配时 exact-replay 续跑 |
| **可复现** | **新增** | 记录 run configuration；可选 pin seed / temperature |

## 一致性硬约束

恢复 **必须** 保持结果一致性：

1. 仅当 `compatibility_fingerprint` 与当前运行完全一致时，才复用已完成阶段输出（exact-replay）。
2. 模型、温度、pipeline/persona/skill、关键 feature flags、report type / analysis phase、Agent/策略源码契约或重新组装的行情/新闻/组合输入任一变化 → **作废检查点并全量重跑**，不会混用新旧输入。
3. 阶段 payload 缺失/损坏 → 作废并全量重跑。
4. `force_full` / `force_refresh` / `ANALYSIS_CHECKPOINT_FORCE_FULL=true` → 忽略已有检查点。
5. 报告 `context_snapshot` 中写入 `analysis_checkpoint` 与 `run_configuration`，标注是否 resumed、consistency 类别。

## 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `ANALYSIS_CHECKPOINT_ENABLED` | `true` | 阶段检查点总开关 |
| `ANALYSIS_CHECKPOINT_DIR` | `./data/checkpoints` | 检查点目录 |
| `ANALYSIS_CHECKPOINT_TTL_HOURS` | `24` | 过期清理（小时；0 关闭） |
| `ANALYSIS_CHECKPOINT_FORCE_FULL` | `false` | 强制全量重跑 |
| `REPRO_MODE_ENABLED` | `false` | 可复现模式（请求级 temperature=0，并在 provider 支持时传递 seed） |
| `REPRO_RECORD_CONFIG` | `true` | 始终记录 run configuration 快照 |
| `REPRO_SEED` | 空 / 0 | 可复现种子 |

API 分析的 `force_refresh=true` 同时会绕过阶段检查点。

## 限制（务必知悉）

- 供应商侧采样即使 temperature=0 也可能非确定性。
- seed 与 temperature 仅按单次请求传递，不修改共享 Config，也不重置进程级 Python/NumPy 随机数状态。
- 实时行情 / 搜索结果在完整运行与稍后重放之间可能变化；exact-replay 复用的是 **已保存的 Agent 阶段输出**，不会对已完成阶段再次调用 LLM。
- 检查点是进程本地文件系统存储，不是分布式队列（ADR-004 / ADR-008）。

## 实现入口

- `src/services/analysis_stage_checkpoint.py`
- 编排接入：`src/core/stages/orchestration.py`、`src/agent/orchestrator_parts/pipeline.py`
- 元数据：`context_snapshot.analysis_checkpoint` / `context_snapshot.run_configuration`
