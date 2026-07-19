# PydanticAI Runtime 采用决策报告（RF-07 证据卷宗）

## 1. 文档状态与用途

- 状态：`Accepted / Implemented`（RF-07 裁决 `Native Only`，2026-07-19 完整实施）
- 版本：v1.1
- 日期：2026-07-19
- 上位决策：`docs/architecture/ADR-001-agent-runtime.md`（`Accepted`）
- 修复计划：`docs/architecture/pydanticai-runtime-recovery-plan.md`（历史，RF-00～RF-07 已结束）
- 用途：汇总 RF-06 阶段已收集的证据并记录 RF-07 裁决。维护者于 2026-07-18 裁决 `Native Only`（recovery plan 默认结论），据此收尾 RF-00～RF-07 修复计划。

本报告只固化“已经证明的事实”与“尚未收集的缺口”，不以脚手架冒充证据。
第 3 节中的实验文件名和 CI 名称是裁决前的历史证据；Native Only 实施后这些
可执行资产已从主线删除，不代表当前支持矩阵。

## 2. 决策框架

recovery plan RF-07 的裁决规则：

- 默认 `Native Only`。
- 仅当 **RF-06 全部硬门禁通过** 且 **有明确收益** 时，维护者才可批准 `Continue Experimental`。
- 即使 `Continue Experimental`：Native 永久默认、可零 PydanticAI 依赖运行；Runtime fallback 默认关闭；不立即新增用户设置；PydanticAI 资产必须继续支持整体删除；Desktop 需独立完成多平台真实打包证据。

因此裁决取决于两组证据：**(A) 契约等价性与安全性**（离线可证）与 **(B) 收益与成本**（需真实 provider 与多平台打包）。

## 3. 已收集证据（离线可证）

### 3.1 契约等价性（RF-06a offline conformance）

`tests/agent/runtime/test_conformance_replay.py` 对每个 `mode=single_run` replay fixture 双跑 Native 与实验 PydanticAI Runtime（同一 `ReplayLLMAdapter` transcript、同一确定性工具 registry），支持矩阵从 manifest 派生：

| 类别 | fixtures | 结论 |
| --- | --- | --- |
| 等价通过 | a/hk/us-single-run-normal、a-single-run-partial、contract-modelref/fallback/toolscope/malformed（8） | 终态分类、dashboard、LLM 调用序列、工具调用序列+参数逐项一致 |
| 有意差异 | contract-timeout、contract-cancelrace ×2（3） | 终态分类等价（三例 Native 与实验侧均为 `TIMED_OUT`）；工具执行日志因 fence 位置不同而不同，记录于 ADR-001 D5 |
| 明确不支持 | CHAT / RESEARCH（及所有非 RUN 模式） | 稳定 `unsupported_capability`，不计作 pass |

- unsupported 不计入 pass；有意差异不重录、不放宽既有 36 个 replay fixture（全程只读）。
- CI：离线 conformance 纳入阻断门 `pydanticai-installed`（`STOCKPULSE_REQUIRE_PYDANTIC_AI=1`，缺失依赖或模块级 skip 判为失败）。

### 3.2 安全性 / 泄漏扫描（RF-06b offline）

`tests/agent/runtime/test_conformance_leak_scan.py`：实验 Runtime 的 provider-error 失败面经 `sanitize_agent_diagnostic` 脱敏——planted 的 API key、credentialed URL、bearer token 均被替换为 `[REDACTED]`，且长度有界（≤300），不外泄原始 provider payload。实证脱敏输出：`upstream request to [REDACTED_URL] failed: authorization=[REDACTED] apikey=[REDACTED] ...`。

### 3.3 依赖足迹（RF-06b offline，实测）

`pydantic-ai-slim==2.12.0` 传递闭包约 22 个包，其中约一半（pydantic、pydantic-core、httpx、anyio、certifi、idna、typing-extensions、annotated-types）已在 StockPulse 现有栈中共享；**净新增约 10 个**（genai-prices、griffelib、opentelemetry-api、pydantic-graph、typing-inspection、logfire-api、truststore、exceptiongroup、h11、httpcore），多为小包。方案 B 用 slim 核心刻意避开了 provider extras 与 tiktoken 冲突（ADR-001 D4 / 议题 #537）。

**初步判断**：纯 source / Docker 的增量打包成本较低。

## 4. 尚未收集的证据（需维护者资源，不得冒充完成）

| 缺口 | 需要 | 原因 |
| --- | --- | --- |
| 真实 provider latency（p50/p95）与成本 | CI secret 中的真实 API key | recovery plan 要求真实 benchmark 独立为 network/Actions artifact、不读开发者 ambient 凭据；本地无法产出真实数字 |
| schema/报告成功率、attribution、error classification 的**真实 provider** 表现 | 同上 | 离线 replay 只能证明契约等价，无法反映真实模型行为分布 |
| Desktop（macOS / Windows）安装/启动/卸载/体积 | 多平台构建机 | recovery plan RF-07 要求 Desktop 独立完成多平台真实打包证据 |

在上述证据补齐前，`Continue Experimental` 所需的“明确收益”无法成立。

## 5. 裁决（RF-07）

**维护者 2026-07-18 裁决：`Native Only`。**

- 依据：契约等价性（3.1）与安全脱敏（3.2）已满足硬门禁的离线部分，依赖足迹（3.3）显示 source/Docker 增量成本可控；但 `Continue Experimental` 另要求“明确收益”，而其收益证据（真实 provider benchmark）与 Desktop 多平台打包证据未收集（第 4 章），故不满足 `Continue Experimental` 的启用条件。
- 生效结果：Native Runtime 是唯一可执行 Runtime；实验 PydanticAI Adapter、toolset、可选依赖清单、内部注入点、cross-runtime 测试和专用 CI 已删除。本轮不新增用户设置、环境变量开关、公开 API 或持久 Agent Job。
- 保留资产：Contract（RF-02）、BoundToolSession（RF-03）、统一生命周期/fence（RF-04）等已在 Native 证明价值的架构收益保留，不随实验资产删除而回滚。
- 重启条件：若未来维护者补齐第 4 章证据，必须另立 ADR 并从当前中立 Contract 重新接入；不得直接恢复历史 Adapter 或把 recovery plan 当作现行指令。

## 6. 回滚

- Native Only 实施可通过整体 revert 对应提交回滚；不得只恢复 Adapter、依赖或 CI 的一部分。
- Contract、BoundToolSession、生命周期、事件、sanitizer 和 Native replay 测试不属于实验资产，不随回滚删除。
