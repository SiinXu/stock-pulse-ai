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
| `scripts/run_agent_benchmark.py` | CLI（Markdown + JSON） |

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
- 替代分析质量面板（[#617](https://github.com/SiinXu/stock-pulse-ai/issues/617)）——后者评 **报告** 夹具，本基准评 **Agent 运行** 纪律

## 与其他工作的关系

| Issue / 面 | 关系 |
| --- | --- |
| #252 | 本离线 V0 切片 |
| #215 | 更广 harness / 反馈 / 自改进 — 范围外 |
| #617 / 分析质量面板 | 互补：报告信任 vs Agent 运行纪律 |
| AR-01 agent_runtime fixtures | 只读转写源 |
| 输出质量评估服务 | 互补：[agent-eval-dimensions.md](agent-eval-dimensions.md) 对单次输出产物打分（`agent_eval_service`）；与本 runtime 基准代码不共享 |
| CI merge queue / workflow 归属 | 本 PR 不改 `.github/workflows/**` |
