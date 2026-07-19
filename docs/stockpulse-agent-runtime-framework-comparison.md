# StockPulse Agent Runtime 框架对比

- 状态:`Historical`（框架 POC 已结束；现行结论以 `docs/architecture/ADR-001-agent-runtime.md` 为准）
- 日期:2026-07-19（记录 Native Only 实施；候选资料仍以 2026-07-17 访问结果为历史快照）
- 代码 baseline:`main@fa7a6ee1`
- 外部资料访问日期:2026-07-17;信息可能过时,引用前须重新核对官方文档

## 1. 本文档的定位与诚实性声明

本文档在 AR-PY-00 阶段**新建**(此前不存在,属治理文档漂移修复,见开发计划第 4.1 节)。因此:

- 不存在需要修正的历史结论(如任何"Vercel Harness"旧结论);首版即以 PydanticAI 为第一优先 Python POC 建立结论。
- 除 PydanticAI 外,其余框架仅做**定位级对比**,未逐一深度核对官方文档;对应格子标注 `未核`,不得作为裁决依据。
- AR-PY-04/05 的隔离 Spike 与 conformance 是历史决策证据，不是当前支持声明。RF-07 已裁决并实施 Native Only。

## 2. 选型前提(由 StockPulse 现状决定,任何框架必须满足)

1. **Native Only**:当前只允许 Native 执行；未来框架必须通过新 ADR 和 Runtime Contract 重新接入(ADR-001 D1/D5)。
2. **不得形成第二套权威**:模型配置/路由、Conversation、Usage、Provider trace、报告 Schema 均归 StockPulse(ADR-001 D3)。
3. **工具只经 BoundToolSession**:fail-closed,不暴露原始 ToolRegistry/handler。
4. **行为逐字节可回归**:36 个 Native replay fixture 保持只读；两个 degraded `success=true` 行为按现状复现(ADR-001 D4)。
5. **无休眠依赖**:未获新 ADR 批准前，不保留外部 runtime 的 Adapter、可选依赖、注入点或专用 CI。
6. **Python 栈**:后端为 Python(FastAPI + LiteLLM);JS/TS 框架需跨语言桥接,直接出局。

## 3. 候选框架对比

| 维度 | PydanticAI | LangGraph | AutoGen | CrewAI | 自研扩展(Native++) |
| --- | --- | --- | --- | --- | --- |
| 语言/栈契合 | Python,Pydantic 同源(StockPulse schemas 即 Pydantic) | Python,LangChain 生态 | Python | Python | 完全契合 |
| 类型化 output | 一等公民(`output_type`,partial validation) | 需组合 LangChain 结构化输出(未核) | 弱(未核) | 弱(未核) | 现状:宽松 JSON repair |
| Model 抽象可替换性 | `Model` 公开可子类化(方案 B 前提成立,2026-07-17 官方文档确认) | 绑定 LangChain Model 生态(未核) | 未核 | 未核 | 不适用 |
| LiteLLM 兼容 | 官方 LiteLLM Model 文档页访问当日 404(**Evidence gap G1**,Spike 验证) | 经 LangChain-LiteLLM(未核) | 未核 | 未核 | 已用 LiteLLM(单一权威) |
| 工具桥接 | `AbstractToolset`(`get_tools`/`call_tool`)可承接 BoundToolSession 中立描述 | Tool 抽象绑定 LangChain(未核) | 未核 | 未核 | 现有 ToolSurface |
| 依赖面 | `pydantic-ai-slim` 变体,extras 可裁剪 | LangChain 生态依赖树大(未核) | 未核 | 未核 | 零新增 |
| 取消语义 | `result.cancel()` 仅 cooperative 承诺(**Evidence gap G2**,Spike 实测) | 未核 | 未核 | 未核 | 本期 AR-PY-03 自建 |
| 许可证 | MIT | MIT(未核实各子包) | 未核 | 未核 | 不适用 |
| 版本节奏 | v2.12.0(2026-07-17),节奏快,需精确 pin(风险 R1) | 未核 | 未核 | 未核 | 不适用 |
| 编排/图/durable | 提供 graph、durable extras——**全部列为第一期禁区** | 以图编排为核心卖点,与"禁区"冲突面大 | 对话式多 Agent 编排,与 Multi 拓扑冲突面大 | 角色编排,同上 | 不适用 |

## 4. 当前结论

1. **Native Only 已实施。** PydanticAI POC 未证明足以抵消真实 provider、Desktop、维护与供应链成本的明确收益，因此其 Adapter、依赖、注入点、测试矩阵和专用 CI 已删除。
2. LangGraph/AutoGen/CrewAI 未获得深度证据或产品化批准，不是休眠的备选实现。
3. AR-PY-01～03 的 Contract、BoundToolSession、生命周期、取消、事件和 sanitizer 已在 Native 证明价值，继续保留。
4. 未来重新评估任何框架时，必须重新核对官方资料、补真实收益和打包证据，并新建 ADR；本历史比较不能直接授权实现。

## 5. 更新记录

| 日期 | 变更 |
| --- | --- |
| 2026-07-17 | 首版创建(AR-PY-00);PydanticAI 列为第一优先 Python POC;其余框架定位级对比并标注未核 |
| 2026-07-19 | RF-07 Native Only 裁决实施；实验资产删除，本文转为历史比较记录 |
