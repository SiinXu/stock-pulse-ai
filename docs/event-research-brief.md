# 事件研究简报（财报优先）

> English: [event-research-brief_EN.md](event-research-brief_EN.md)

Issue #1131。基于托管公司事件触发的结构化 EventBrief（首日 earnings）。

- 独立路径：`EVENT_RESEARCH_BRIEF_ENABLED`（默认关）。
- 字段：关注指标、超预期定义、关联假设、事后核对清单、verify_hook。
- 服务只消费托管 `intelligence_items` 公司事件触发，阶段标记为 `observed_event_review`；不声称具备未来事件目录（#153）。
- 已落库 JSON 诊断采用严格解析；包含无效或非有限数值的载荷会被拒绝，不进入展示。
- 每日晨报通过兼容键 `event_foresight` 嵌入近期事件上下文；不新增 Agent 工具。
- 单份简报上限 12,000 字符，组合通知上限 24,000 字符。
- 任务名为 `event_research_brief`；通知复用统一 `report` 路由并隔离逐渠道失败，运行进程内发送失败可重试。
