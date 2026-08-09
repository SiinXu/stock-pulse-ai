# Risk Manager 最终动作裁决

Risk Manager 是每个 buy、hold、sell 建议发布前的强制、确定性最终裁决者。
它扩展 `src/agent/risk_override.py`，不会新增平行风控引擎，也不会调用 LLM。

## 覆盖出口

- 多 Agent 与投资委员会的 dashboard 定稿
- 单 Agent dashboard 转换
- 多策略合议在后续护栏完成后的最终投影
- Agent Chat 在返回响应和写入会话历史之前

每个出口都把真实 dashboard 与有界 runtime 风险证据投影到同一个评估器。
评估器返回的最终动作继续用于 dashboard、`AnalysisResult`、报告、通知、API
payload、持久化 raw report、DecisionSignal metadata 和聊天历史。

## 裁决与档位

标准裁决只有 `pass`、`downgrade`、`reject`。每次结果使用有界的
`risk-manager-result/v1` 结构，包含原始动作、最终动作、原因/证据 code、档位、
出口 ID、评估 ID、时间戳及可选的一次性授权 ID；不会持久化原始 Prompt 或
模型推理。

`RISK_GATE_PROFILE` 支持：

| 档位 | 策略 |
| --- | --- |
| `conservative` | 任一受支持的高风险证据均会介入，明确 veto 会被 reject。 |
| `balanced` | 默认；方向冲突、veto、高危旗标和明确降级指令会触发下调。 |
| `aggressive` | 仅在明确阻断证据或已启用的 legacy override 转换时介入。 |

非法值会阻止配置加载。闸门不可关闭。既有 `AGENT_RISK_OVERRIDE` 仍控制 legacy
override 计划，但关闭它不能绕过最终动作裁决。

单纯缺少证据时返回 `pass`，不会伪造风险。包含非法有界字段或畸形时间戳的证据
会标记为 invalid 并阻止新的 bullish 发布；带时间戳且早于 24 小时的证据会保留
来源、标记 stale，并同样阻止新的 bullish 发布。

## 失败与授权语义

内部评估异常采用 fail-closed：buy 变为 hold，并记录 `reject`、
`gate_internal_failure`、`fail_closed=true`，不会意外发布原始 buy。

运行恢复时，应检查结构化结果中的稳定诊断字段 `exception_type`、`exit_id` 和
`evaluation_id`，修复非法配置/证据或运行时故障后重新执行分析。恢复过程不得
关闭或绕过闸门；若工作正常的闸门建议改变动作，只有一次性审批可授权保留原动作。

`/approvals` 仍提供可选的一次性旁路。授权被消费后保留原始动作，在结构化结果
中记录审批 ID，并明确显示“经授权保留原始动作”，不能误称“已下调”。

## 回滚

回退对应变更即可。新增持久化内容均为附加 JSON metadata，无数据库迁移。
不要以新增关闭开关作为回滚方式。
