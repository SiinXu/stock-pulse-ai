# Risk Manager 决策门

Issue #120 的强制决策出口风控评估。本能力**升级**既有
`src/agent/risk_override.py`，不新建平行风控引擎，也不改最终报告 JSON schema。

## 调用路径图（当前）

```
单 Agent（AgentExecutor dashboard）
  → analysis_results._agent_result_to_analysis_result
  → apply_risk_manager_gate(exit=single_agent)

多 Agent / 投资委员会
  → orchestrator dashboard 定稿
  → _apply_risk_override
  → apply_risk_manager_gate(exit=orchestrator_multi_agent|committee_mode)
  → 既有 AGENT_RISK_OVERRIDE 计划 + 可选 HITL 旁路

Deliberation 修订投影
  → analysis_agent（开启 multi-strategy deliberation 时）
  → apply_risk_manager_gate(exit=deliberation_projection)
  → build_pipeline_final_explanation（仅解释）

Agent Chat 问股
  → orchestrator_parts.chat.chat
  → apply_risk_manager_gate(exit=agent_chat)
```

每一条决策出口**必须**过门；缺一条视为未完成。

## 三种结果

| 结果 | 信号 | 用户可见 |
| --- | --- | --- |
| `pass` | 不变 | 无强制提示 |
| `attach_warning` | 不变 | 在 `risk_warning` 追加 `[Risk Manager] ...` |
| `downgrade` | 更保守 | 改信号 + 强制提示 |

判定规则为**确定性**条件（风险旗标、veto、signal_adjustment、证据与结论矛盾、
置信度与证据不匹配），**不再调用 LLM**。

## 配置

| 环境变量 | 默认 | 含义 |
| --- | --- | --- |
| `RISK_GATE_ENABLED` | `true` | 每个出口都执行门评估 |
| `RISK_GATE_STRICT` | `false` | 有风险证据时强制降级（即使 `AGENT_RISK_OVERRIDE=false`） |
| `AGENT_RISK_OVERRIDE` | `true` | 既有强制降级权威（计划 `will_apply` 时） |

**默认模式取舍**：默认只附加风险提示。把所有既有 buy 强制降级属于破坏性变更；
严格模式需显式开启。

## 留痕与 fail-safe

- 每次评估写入 `ctx.meta["risk_gate_result"]` 与
  `ctx.data["risk_gate_applied"]`（低敏 dict，可供 T03 类 trace 消费）。
- 门自身异常时分析继续，保留原信号，并记录 `fail_safe=true` /
  `gate_internal_failure`。

## 兼容性

- 不替换 `AGENT_RISK_OVERRIDE` / HITL 审批旁路。
- 不改 `runner.py` 日志格式与报告 schema 字段。
- Web Settings 注册表项刻意延后（配置注册表归属其他任务）；环境变量默认即可运行。

## 回滚

设置 `RISK_GATE_ENABLED=false`，或 revert 对应 PR。无数据迁移。
