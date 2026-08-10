# 离线金融 Agent 评测基准（V0）

**状态**：Issue [#252](https://github.com/SiinXu/stock-pulse-ai/issues/252) 的 **离线阶段 V0**  
**互补**：评测与自改进总单 [#215](https://github.com/SiinXu/stock-pulse-ai/issues/215)；分析质量面板 Phase A [#617](https://github.com/SiinXu/stock-pulse-ai/issues/617) / [analysis-quality-panel.md](analysis-quality-panel.md)  
**English**: [agent-eval-benchmark_EN.md](agent-eval-benchmark_EN.md)

## 目的

对**已录制的 Agent 运行结果**（而非自由生成的 LLM 散文）按三类可度量检查打分：

| 族 | 检查内容 |
| --- | --- |
| `financial_task_correctness` | 终端成功、决策信号、仪表盘必填字段、标的身份 |
| `tool_usage_discipline` | 必用/禁用工具、股票代码作用域、成功/失败策略、调用次数上限 |
| `uncertainty_honesty` | 风险提示、允许的置信度、缺口表述 / 非平凡 `data_limitations` |

全部为**离线**：冻结的 `tests/fixtures/agent_runtime/**` 转写、`ReplayLLMAdapter` 与确定性本地工具。无网络、无真实 LLM。

## 布局

| 路径 | 作用 |
| --- | --- |
| `tests/fixtures/agent_runtime/benchmark/manifest.json` | 场景目录（3–6 个） |
| `tests/fixtures/agent_runtime/benchmark/scenarios/*.json` | 评分细则 + 指向既有 AR-01 fixture 的 `source_case` |
| `tests/agent/benchmark/loader.py` | Manifest / baseline 路径 |
| `tests/agent/benchmark/metrics.py` | 确定性检查函数 |
| `tests/agent/benchmark/runner.py` | 回放 + 打分 + 报告 |
| `tests/agent/benchmark/baselines/v0.json` | 已提交的基线分数 |
| `tests/agent/benchmark/test_offline_benchmark.py` | pytest 入口（`@pytest.mark.benchmark`） |
| `scripts/run_agent_benchmark.py` | CLI（Markdown + 完整 JSON，含轨迹评估） |

场景只**引用**既有 agent_runtime fixture，不重冻、不改 AR-01 基线；主 `manifest.json` 保持不动。

## 如何运行

```bash
# 推荐本地 / 维护路径
python scripts/run_agent_benchmark.py

# 可选产物
python scripts/run_agent_benchmark.py \
  --json-out /tmp/agent-eval.json \
  --md-out /tmp/agent-eval.md

# pytest 入口（被阻塞性 offline gate 排除）
python -m pytest -m benchmark tests/agent/benchmark -q
```

阻塞性 backend gate 使用 `pytest -m "not network and not benchmark"`，因此本套件在 V0 默认**不阻塞合入**。

CLI 本身就是显式选择加入的边界。不存在运行时
`AGENT_TRAJECTORY_EVAL_ENABLED` 配置：生产分析路径并不调用本评估器，发布
一个无消费者的环境变量只会形成第二套配置所有者。

## 轨迹评估契约

完整 `--json-out` 产物的每个 `scenario_details[]` 都包含带版本的
`trajectory_evaluation`。已提交 baseline 仍是精简的仅分数视图，本次不扩写、
不重置 baseline。

评估器消费 runner 已脱敏的 `tool_calls` 字段：`step`、`tool`、
`arguments`、严格布尔的 `success` / `cached`、可选严格布尔的 `timeout` /
`guarded`、`duration` 及有界 guard 元数据。Benchmark 补充稳定的场景 task
ID、源 run ID、回放 execution ID、市场与标的身份。原始参数体不会出现在
结果中，只保留有界规范化内容的 SHA-256 指纹。

| 指标 | 确定性语义 |
| --- | --- |
| `tool_selection_precision` | 工具属于场景 `required_tools` 的调用数 / 接受调用数 |
| `tool_selection_recall` | 已出现的必需工具去重数 / 必需工具去重数 |
| `tool_selection_f1` | 上述两个选择指标的调和平均 |
| `tool_call_success_rate` | 成功调用 / 接受调用；绝不命名为选择质量 |
| `productive_step_rate` | 成功且非冗余调用 / 接受调用 |
| `redundancy_rate` / `retry_rate` | 因果上更晚、同工具同参数且前次成功 / 失败的调用比例 |
| `cache_hit_rate` | `cached=true` 的接受调用比例 |
| `task_completion_rate` | 明确终态成功的 run / 终态已知 run |

场景没有预期工具标注时，选择指标为 `null`。错误但执行成功的工具可以提高
调用成功率，却不能提高选择 precision/recall/F1；重复全失败重试的 productive
step rate 为零。

### 因果与所有权

指纹历史按 `run_id` 与 `agent_id` 隔离，因果关系不由列表位置推导。对每个
`(agent_id, tool, 参数指纹)` 作用域，评估器先在整个 run 上聚合出最早出现的
因果位置与最早**成功**的因果位置（位置取 `dispatch_index`，缺失时取 runner
`step`），随后判定：

- **冗余（redundant）**：存在严格更早位置上的同指纹成功调用；
- **重试（retry）**：存在严格更早位置上的同指纹调用，但这些更早调用全部失败；
- 其余情况两者皆否。

由于该聚合只依赖 `(位置, 成功)` 的多重集合，同位置（并行）结果的完成顺序
永远无法把更晚的依赖调用在 `retry` 与 `redundant` 之间翻转。同 step 并行调用、
没有因果位置的调用、不同 agent 及不同 run，绝不会仅因完成列表顺序靠后就被
误判为成功后的冗余。

### 评估标识

`evaluation_id` 是对完整规范化结果的 SHA-256：rubric 指纹、路径标签、`as_of`、
schema/引擎/rubric 版本、run 来源信息、每个已评估 step 的全部字段（位置、
duration、缓存状态、失败分类、因果分类、时间戳）、完整度量集合，以及拒绝与
截断证据。因此任何改变度量或 step 字段的输入差异——包括仅 duration 或
`cached` 不同——都会改变 `evaluation_id`。输出侧的 step 截断是该载荷的确定性
函数，因此相同标识必定序列化为相同结果。

### 校验、边界与来源

- 字符串布尔值、空工具名、非有限/负数/超大 duration、未知路径标签、
  非 JSON 参数及过大/过深参数会被拒绝并计数，绝不静默强制转换。
- 评估上限为 64 run / 2,000 个接受源调用；返回 step 明细上限 1,000，
  严格 JSON 结果上限 500,000 字符。源截断与输出截断均显式记录。
- 超大输入只截断、不致命。远超接受调用上限的输入仍返回有界结果并置
  `source_truncated=true`；聚合 `rejected_call_count` 在 128,000 处饱和并置
  `rejected_call_count_saturated=true`，避免静默少报拒绝数量；单个 run 的来源
  信息仍保留未饱和的精确计数。
- 每个结果携带确定性的 evaluation/rubric 指纹、输入/引擎 schema 版本、
  run/execution/task/agent/call ID、可用的标的/市场、拒绝计数及源/输出截断状态。
- 当前冻结 fixture 不记录 dispatch 时间、token/tool budget 或子 agent 身份；
  这些维度保持不可用，不做推断。Runner/core 文件保持不变。

## 如何解读分数

- **Score** = 全部场景与检查族上的 `checks_passed / checks_total`。
- 场景的 `failed_checks` 列出失败检查 id 与细节。
- 与基线对比时输出 **delta**；下降场景标 **DROP**。

### V0 策略

| 事件 | 行为 |
| --- | --- |
| 基础设施 / fixture 加载失败 | Runner 非零退出 |
| 当前 HEAD 上度量检查失败 | 报告中展示；端到端 pytest 期望当前面板满分，可选 `@benchmark` 套件会失败 |
| 相对已提交基线分数下降 | Markdown 报告中**可见**；CLI 默认仍 exit 0 |
| 下降即硬失败 | 仅 `--strict-baseline`（可选） |

分数下降供维护者诊断，V0 **不是**必需 CI gate。`.github/workflows/**` 的定时任务接线为本 PR 的**后续事项**（CI 工作流另有归属）。

## 刷新基线

在**有意**变更 runtime 或 fixture 并正确改变分数后：

```bash
python scripts/run_agent_benchmark.py --write-baseline
```

将 `tests/agent/benchmark/baselines/v0.json` 与英文 changelog 说明一并提交。不要用改基线掩盖意外回归。

## 新增场景

1. 优先复用 `tests/fixtures/agent_runtime/` 下既有离线 fixture（financial 或 contract）。
2. 新增 `tests/fixtures/agent_runtime/benchmark/scenarios/<id>.json`，包含：
   - 相对 `tests/fixtures/agent_runtime/` 的 `source_case`
   - 含全部三个 metric family 的 `evaluation`
3. 在 `benchmark/manifest.json` 注册。
4. 保持面板精简（V0 建议 ≤6 个场景）。
5. 连续运行 runner 两次，确认 JSON 输出一致。
6. 若分数有意变化，按上文刷新基线。

## 明确不主张

- 市场收益、排序质量或 alpha
- 在线数据源准确率或网络 SLA
- 主观文案质量作为合入门禁
- 完整 Agent 自改进闭环（[#215](https://github.com/SiinXu/stock-pulse-ai/issues/215)）
- 线上/运行时轨迹采集，或超出场景 rubric 的 oracle 级选择标签（[#269](https://github.com/SiinXu/stock-pulse-ai/issues/269)）
- 替代分析质量面板（[#617](https://github.com/SiinXu/stock-pulse-ai/issues/617)）——后者评 **报告** 夹具，本基准评 **Agent 运行** 纪律

## 与其他工作的关系

| Issue / 面 | 关系 |
| --- | --- |
| #252 | 本离线 V0 切片 |
| #269 | 轨迹指标已接入本 benchmark；线上跟踪与更丰富标签仍保持开放 |
| #215 | 更广 harness / 反馈 / 自改进 — 范围外 |
| #617 / 分析质量面板 | 互补：报告信任 vs Agent 运行纪律 |
| AR-01 agent_runtime fixtures | 只读转写源 |
| 输出质量评估服务 | [agent-eval-dimensions.md](agent-eval-dimensions.md) 对单次输出产物打分（`agent_eval_service`），由本统一 runner 调用并单独计分 |
| CI merge queue / workflow 归属 | 本 PR 不改 `.github/workflows/**` |
