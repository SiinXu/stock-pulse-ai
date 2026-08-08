# 金融 Agent 输出质量评估维度（输出侧 V1）

**状态**：Issue [#252](https://github.com/SiinXu/stock-pulse-ai/issues/252) 输出质量切片；失败挖掘 [#141](https://github.com/SiinXu/stock-pulse-ai/issues/141)；harness 部分 [#215](https://github.com/SiinXu/stock-pulse-ai/issues/215)  
**English**: [agent-eval-dimensions_EN.md](agent-eval-dimensions_EN.md)  
**互补**：既有 **运行时结构** 基准 [agent-eval-benchmark.md](agent-eval-benchmark.md)（`tests/agent/benchmark`）评估工具调用过程纪律；本表与 `src/services/agent_eval_service.py` 评估 **单次输出产物** 质量。二者指标口径对齐、代码不共享。

## 目的

在改 prompt / 工具 / 模型后，用**可离线重放**的 case 回答：输出质量是变好还是变差？失败集中在哪些模式？

## 维度表

| 维度 id | 检验什么 | 判定方式 (`judge`) | 稳定性说明 |
| --- | --- | --- | --- |
| `factuality` | 输出中的行情/财报类数值是否能在输入上下文中找到来源（禁止编造数字） | **rule**（确定性） | 同一 case 重复运行字节级稳定；对数字格式（逗号、尾零、`%`）做规范化 |
| `tool_usage` | 是否调用必用工具、是否触碰禁用工具（基于输出侧 `tool_calls` 记录） | **rule** | 稳定；与 T01 trajectory 效率指标分工：本维只看对错集合，不看步数/耗时 |
| `conclusion_consistency` | 证据极性与最终信号是否矛盾（如证据全看空却 `buy`） | **rule** | 稳定；依赖 case 中结构化 `evidence[].polarity|sentiment` |
| `boundary_honesty` | 数据缺失/工具失败时是否过度自信（高置信 + 强硬方向 + 无缺口说明） | **rule** | 稳定；上下文需标记 `data_missing` / `failed_tools` |
| `language_format` | 必填字段、禁止用语、JSON/对象形态等格式与语言规则 | **rule** | 稳定 |
| `explanation_clarity` | 解释是否清晰、可读（主观） | **llm**（可选外部判定） | **不进入 rule 总分**；离线默认 `skipped`；仅当调用方显式传入 `llm_judgements` 才计分 |
| `risk_framing_quality` | 风险表述质量（主观） | **llm**（可选） | 同上：单独 `llm_score`，永不与 rule 混计 |

## 计分规则

- **Rule score** = 全部 rule 检查的 `passed / total`（跳过项不计）。
- **LLM score** = 仅 `judge=llm` 且未 skipped 的检查；与 rule 分**分开报告**。
- 失败挖掘：按 `(dimension, check_id)` 聚类，输出 case id 清单与样本 detail，而不是只给一个总分。

## 布局

| 路径 | 作用 |
| --- | --- |
| `src/services/agent_eval_service.py` | 评估执行器 + 失败挖掘 |
| `tests/fixtures/agent_eval/manifest.json` | case 目录 |
| `tests/fixtures/agent_eval/cases/*.json` | 输入上下文 + 期望性质 + 冻结 `agent_output` |
| `tests/services/test_agent_eval_service.py` | 离线 pytest（每条规则含反例） |

## 开关

```bash
# 默认关闭；关闭时 evaluate_suite 直接返回 enabled=False，对生产链路零影响
AGENT_EVAL_ENABLED=false
```

## 如何运行

```bash
# 启用后在 Python 中跑内置 fixture 套件
AGENT_EVAL_ENABLED=true python -c "
from src.services.agent_eval_service import AgentEvalService, format_failure_report
r = AgentEvalService().evaluate_suite()
print('rule_score', r.rule_score)
print(format_failure_report(r))
"

python -m pytest tests/services/test_agent_eval_service.py -q
```

## 明确不做

- **不**自动改写 prompt / skill（#215 自我改进剩余范围）
- **不**修改 `src/agent/`、runner、backtest / decision-signal outcome 服务
- **不**用全局胜率伪造 skill 级绩效（延续 `BacktestService.get_skill_summary()` 返回 `None` 的诚实原则）
- **不**替代 V0 runtime benchmark 或 analysis-quality 面板

## 与 T01 trajectory 评估的关系

| | T01 trajectory | 本服务（输出质量） |
| --- | --- | --- |
| 对象 | 工具调用过程效率 | 输出内容质量 |
| 代码 | 独立（本任务不共享） | `agent_eval_service.py` |
| runner | 均不得修改 | 均不得修改 |
