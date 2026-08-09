# 金融 Agent 输出质量评估维度（输出侧 V1）

**状态**：Issue [#252](https://github.com/SiinXu/stock-pulse-ai/issues/252) 输出质量切片；失败挖掘 [#141](https://github.com/SiinXu/stock-pulse-ai/issues/141)；harness 部分 [#215](https://github.com/SiinXu/stock-pulse-ai/issues/215)

**English**: [agent-eval-dimensions_EN.md](agent-eval-dimensions_EN.md)

**集成**：`tests/agent/benchmark` 的统一离线 runner 同时运行 runtime 结构检查和本单次输出质量套件。

## 目的

在改 prompt / 工具 / 模型后，用**可离线重放**的 case 回答：输出质量是变好还是变差？失败集中在哪些模式？

## 维度表

| 维度 id | 检验什么 | 判定方式 (`judge`) | 稳定性说明 |
| --- | --- | --- | --- |
| `factuality` | 每条数值 claim 必须按 fact id、字段路径、值、单位、时间和来源精确绑定 | **rule**（确定性） | 阻止跨字段借值及百分比/绝对值混用 |
| `tool_usage` | 必用工具须完成、成功、结果有效且已授权；禁用工具不得尝试 | **rule** | 仅接受精确布尔值；仅出现工具名不能通过 |
| `conclusion_consistency` | 证据极性与最终信号是否矛盾（如证据全看空却 `buy`） | **rule** | 稳定；依赖 case 中结构化 `evidence[].polarity|sentiment` |
| `boundary_honesty` | 数据缺失/工具失败时是否过度自信（高置信 + 强硬方向 + 无缺口说明） | **rule** | 稳定；上下文需标记 `data_missing` / `failed_tools` |
| `language_format` | 必填字段、禁止用语、JSON/对象形态等格式与语言规则 | **rule** | 稳定 |
| `explanation_clarity` | 解释是否清晰、可读（主观） | **llm**（可选外部判定） | **不进入 rule 总分**；离线默认 `skipped`；仅当调用方显式传入 `llm_judgements` 才计分 |
| `risk_framing_quality` | 风险表述质量（主观） | **llm**（可选） | 同上：单独 `llm_score`，永不与 rule 混计 |

## 计分规则

- **Rule score** = 全部 rule 检查的 `passed / total`（跳过项不计）。
- **LLM score** = 仅 `judge=llm` 且未 skipped 的检查；与 rule 分**分开报告**。
- 失败挖掘：按 `(dimension, check_id)` 聚类，输出 case id 清单与样本 detail，而不是只给一个总分。
- 空/畸形输出、缺 rubric、非有限数和错误类型均为显式 `invalid` 失败，不存在空集通过。
- 候选与基线分别保留 rule/LLM delta、逐维 rule delta、样本量、suite hash 及 agent/config 版本；`--strict-baseline` 在回归时非零退出。
- 报告使用 strict JSON（禁止 `NaN`/无穷）、最多 64 个 case、最多 500,000 字符，并披露截断和丢弃计数。

## 布局

| 路径 | 作用 |
| --- | --- |
| `src/services/agent_eval_service.py` | 评估执行器 + 失败挖掘 |
| `tests/fixtures/agent_eval/manifest.json` | case 目录 |
| `tests/fixtures/agent_eval/cases/*.json` | 输入上下文 + 期望性质 + 冻结 `agent_output` |
| `tests/services/test_agent_eval_service.py` | 离线 pytest（每条规则含反例） |

## 如何运行

```bash
# 显式运行内置 fixture 套件
python -c "
from src.services.agent_eval_service import AgentEvalService, format_failure_report
r = AgentEvalService().evaluate_suite()
print('rule_score', r.rule_score)
print(format_failure_report(r))
"

python -m pytest tests/services/test_agent_eval_service.py -q
python scripts/run_agent_benchmark.py --strict-baseline

# 将具名候选 fixture 目录/config 与冻结基线比较
python scripts/run_agent_benchmark.py --strict-baseline \
  --output-quality-candidate-root /path/to/candidate/catalog \
  --candidate-agent-version agent-v2 \
  --candidate-config-version config-v2 \
  --json-out /tmp/agent-eval.json
```

没有环境开关或生产 runtime hook；显式调用就是 opt-in 边界。fixture 只能包含冻结且无秘密的证据，不得存储私有 prompt、凭据或原始敏感工具 payload。

## 明确不做

- **不**自动改写 prompt / skill（#215 自我改进剩余范围）
- **不**修改 `src/agent/`、backtest / decision-signal outcome 服务
- **不**用全局胜率伪造 skill 级绩效（延续 `BacktestService.get_skill_summary()` 返回 `None` 的诚实原则）
- **不**替代 V0 runtime benchmark 或 analysis-quality 面板

## 与 T01 trajectory 评估的关系

| | T01 trajectory | 本服务（输出质量） |
| --- | --- | --- |
| 对象 | 工具调用过程效率 | 输出内容质量 |
| 代码 | 独立 scorer | `agent_eval_service.py` |
| runner | 统一离线 benchmark | 同一 runner、分开计分 |
