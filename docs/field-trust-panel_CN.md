# 字段级数据信任面板

Issue 引用：#1129。实现位于 `src/data_provider/field_trust.py`，并在 `src/data_provider/base.py` 与 `src/data_provider/realtime_types.py` 中做最小接线。HTTP 视图为 `GET /api/v1/stocks/{code}/trust`。Web 面板挂载在股票工作台（`/stocks/<code>`）。导出的 `FieldTrustPanel` 也已注册到真实 playground 目录。

English: [field-trust-panel.md](field-trust-panel.md)

## 契约

字段级信任是现有实时行情回退链上的附加元数据。它从不替换主观测值，也从不在来源不一致时悄悄选定某一个 provider 作为真相。

| 表面 | 返回内容 |
| --- | --- |
| Quote `field_trust` | schema、逐字段 source/origin/lag/staleness/conflict、冲突检查、provider 尝试/健康、分析输入 |
| API `StockFieldTrustResponse` | `status`（`ok` / `degraded` / `unavailable`）、相同的字段行、冲突、provider 健康，以及 `analysis_input` |
| 分析输入 | 与 provider 无关的 `{ confidence, gaps[] }`；仅当每个覆盖字段都新鲜、已归因且无冲突时才为 `high`。`AnalysisContextBuilder` 把有界 `{confidence, conflict_count, gap_codes, failed_provider_count}` 写入 quote block metadata。非 high 载荷（冲突、过期、未归因、provider 失败、跳过比较、缺失/旧载荷）会把 quote block 标为 `partial`（或保留 `stale`/`fallback`），从而触发既有核心降级规则，禁止 `confidence_level=High`。完整 `field_trust` 不会作为 quote item 拷贝。 |
| 报告摘要 | Jinja 分析报告（`templates/report_markdown.j2`，以及同一 renderer 的 wechat/brief）从该有界 pack metadata 渲染一小段来源 / 置信度 / 缺口 / 冲突数摘要。公开 overview 的 quote block 已带 `source`、`status` 和 `quote_trust_*` 告警；报告据此还原相同缺口，不再请求 `/trust` 或 `get_realtime_quote`。缺失行情且无信任告警时失败关闭为 `quote_unavailable`，不再渲染空缺口。新鲜无冲突行情保持 `confidence=high` 且缺口为空。缺失 overview 时省略该段，不编造降级。 |
| Web 报告页 | `AnalysisContextSummary` 把同一 overview quote 的 `source` / `status` / `quote_trust_*` 告警本地化为低敏行情可信度行，并把缺失行情块映射为 `quote_unavailable`。它不会挂载完整 `field_trust`、provider attempts 或熔断 blob。 |
| Web 面板 | 对过期、冲突、缺失元数据、provider 失败和不可用行情给出可见降级 |

`status=ok` 仅保留给完整、新鲜、已归因、无冲突，且 provider 健康行全部为 `ok` 的视图。缺失元数据、未知过期状态、跳过的冲突检查（包括失败关闭的比较）、过期字段、冲突、首选 provider 失败、后续来源为空/失败/不可用的补充尝试，以及 `available=false` 的熔断快照，都是降级信号。它们不得与 `status=ok` 或分析 `confidence=high` 并存。跨来源身份使用与字段归因相同的 source token（`efinance`、`akshare_em`），而不是 fetcher 类名。Provider 健康行保留这些公开 token，但按尝试上携带的精确 route/circuit 键查找熔断快照，因此一条 CN `akshare_em` 行不能继承 ETF 或 HK 熔断。Web 面板从 `FIELD_TRUST_TEXT` 本地化已知 status 与 gap 代码；后端英文 `message`/`detail` 字符串不应优先于该文案。

## 与 #1133 的所有权边界

本车道只拥有信任契约。分析投影是稳定、与 provider 无关的接口（`gaps` + `confidence`）。它不编译监控、告警规则或自然语言短语。

## 兼容性

- `UnifiedRealtimeQuote.field_trust` 是可选的。缺失元数据必须按未知处理，绝不可信任。
- Quote `to_dict()` 在存在时包含 `field_trust`。分析消费走 `_to_dict(realtime_quote)` 加上有界 `analysis_input` 投影；拿到嵌套对象并不等于把它当成已信任。
- 记录辅助函数对数据失败开放（从不打断行情路径），对信任失败关闭（缺失或旧载荷视为未知，绝不可为 `high`）。

## 回滚

回退引入该能力的变更。不需要配置键；禁用 `DATA_VALIDATION_ENABLED` 会记录跳过的冲突检查，而不是暗示一致。
