# PydanticAI Runtime 采用决策报告（RF-07 证据卷宗）

## 1. 文档状态与用途

- 决策状态：`Amended`（RF-07 裁决 `Native Only` 并于 2026-07-19 实施；同日维护者以 ADR-002 改判恢复实验 Runtime，见第 7 章）
- 证据状态：`Historical / Partial`（只保留已证明的离线子集，不代表 RF-06 全部证据完成）
- 版本：v1.4
- 日期：2026-07-19
- 上位决策：`docs/architecture/ADR-001-agent-runtime.md`（`Accepted`）
- 改判决策：`docs/architecture/ADR-002-pydanticai-runtime-reinstatement.md`（`Accepted`，2026-07-19）
- 修复计划：`docs/architecture/pydanticai-runtime-recovery-plan.md`（历史，RF-00～RF-07 已结束）
- 用途：汇总 RF-06 阶段已收集的证据并记录 RF-07 裁决。维护者于 2026-07-18 裁决 `Native Only`（recovery plan 默认结论），据此收尾 RF-00～RF-07 修复计划。

本报告只固化“已经证明的事实”与“尚未收集的缺口”，不以脚手架冒充证据。
第 3 节中的实验文件名和 CI 名称是裁决前的历史证据；Native Only 实施后这些
可执行资产曾从主线删除，2026-07-19 经 ADR-002 改判恢复（见第 7 章），但第 3
节仍只描述当时实际执行过的证据，不代表当前支持矩阵。无论资产是否在主线，
历史证据状态都不会从 `Partial` 自动提升为 `Complete`。

## 2. 决策框架

recovery plan RF-07 的裁决规则：

- 默认 `Native Only`。
- 仅当 **RF-06 全部硬门禁通过** 且 **有明确收益** 时，维护者才可批准 `Continue Experimental`。
- 即使 `Continue Experimental`：Native 永久默认、可零 PydanticAI 依赖运行；Runtime fallback 默认关闭；不立即新增用户设置；PydanticAI 资产必须继续支持整体删除；Desktop 需独立完成多平台真实打包证据。

因此裁决取决于两组证据：**(A) 契约等价性与安全性**（离线可证）与 **(B) 收益与成本**（需真实 provider 与多平台打包）。

## 3. 已收集证据（历史离线子集）

### 3.1 契约等价性（RF-06a offline conformance）

历史 PR #32（head `099ee702`，merge `d322743f`）中的
`tests/agent/runtime/test_conformance_replay.py` 在下表 8 个“等价通过” case 中
使用同一 `ReplayLLMAdapter` transcript 和确定性工具 registry，真实双跑
Native 与实验 PydanticAI Runtime。另外 3 个“仅终态分类等价” case 没有
重跑 Native；它们只执行实验 Runtime，并将终态与已由 Native 兼容套件冻结的
fixture `expected` block 对照。该测试曾由 RT-01 删除，后由 ADR-002 按同一显式
fixture ID 集合恢复；下表仍只冻结当时实际证明的边界，不因恢复而扩大支持矩阵：

| 类别 | fixtures | 结论 |
| --- | --- | --- |
| 等价通过（8） | `a-single-run-normal`、`hk-single-run-normal`、`us-single-run-normal`、`a-single-run-partial`、`contract-modelref-single-mismatch`、`contract-fallback-provider-error`、`contract-toolscope-unknown-tool`、`contract-malformed-dashboard-repaired` | Native 与实验侧均真实执行；终态分类、dashboard、LLM 调用序列、工具调用序列和参数逐项一致 |
| 仅终态分类等价（3） | `contract-timeout-agent-wallclock`、`contract-cancelrace-single-slow-tool`、`contract-cancelrace-parallel-late-tool` | 只执行实验侧；其 `TIMED_OUT` 与 Native frozen `expected` block 分类一致，没有当场重跑 Native；工具执行日志因历史 fence 位置不同而不同 |
| 明确不支持（2 个直接调用） | `ExecutionMode.CHAT`、`ExecutionMode.RESEARCH` | 历史 adapter 直接调用稳定返回 `unsupported_capability`，不计作 pass |

- 旧实现先筛选 `mode=single_run`，再以 `profile in {timeout, cancelrace}`
  自动划入终态分类例外；这种 profile 级规则会让未来同 profile fixture 静默扩大
  历史证据范围。证据范围现在只认上表三个精确 ID，**不得按 `profile` 自动扩展**。
- `contract-timeout-pipeline-budget-skip` 是 `mode=standard` 的 degraded-success
  fixture，从未进入该 Single RUN 双跑；旧的 `contract-timeout` 简写会掩盖这个边界。
- manifest 中 quick/standard/full/specialist 等其它模式没有进入 cross-runtime 双跑，
  也没有被上述两个 direct capability test 覆盖；它们属于矩阵外，不得计作
  unsupported pass。
- unsupported 不计入 pass；三个终态分类例外不重录、不放宽既有 36 个 replay
  fixture（全程只读）。未来若重新引入 conformance，必须显式列出 case ID，未知
  fixture fail closed，并通过新的 ADR 审批。
- 历史 CI 曾把离线 conformance 纳入 `pydanticai-installed` 阻断门；该 job 与
  cross-runtime 测试曾由 RT-01 删除，现已由 ADR-002 按上述显式范围恢复。

### 3.2 安全性 / 泄漏扫描（RF-06b offline）

历史 `tests/agent/runtime/test_conformance_leak_scan.py` 只验证了一个
provider-error 终端诊断：planted API key、credentialed URL 和 Bearer token 经
`sanitize_agent_diagnostic` 脱敏，且公开错误长度不超过 300 字符。它没有覆盖
prompt、reasoning/provider trace、完整 tool result、日志/artifact 或其它原始异常
路径，因此不能代表 RF-06 泄漏扫描全部完成。

RT-01 删除实验 Runtime 后，把这段已证明的最小回归迁入当前
`tests/agent/runtime/test_native_adapter.py`：Native execution 记录 `FAILED`、不生成
result/dashboard、公开诊断脱敏且有界，同时内部仍抛回同一个异常。其余失败面仍是
未收集的历史证据，不能从 provider-error 个例外推。当前证据治理门禁也会
直接执行该 Native 异常契约，不再仅凭回归测试文件存在就宣称证据保留。

### 3.3 依赖足迹（RF-06b，证据不足）

历史提交只保存了 `pydantic-ai-slim==2.12.0` 的可选 manifest 和安装态 CI，
**未保存可复现的双环境依赖快照**、解析后的 lock/report、完整命令输出、Python/
平台元数据或 artifact hash。因此原先的传递闭包和净新增包数量无法从仓库重建，
相关数字与“增量成本较低”的结论已删除。

ADR-002 恢复后，`requirements-pydanticai.txt` 现精确锁定 PydanticAI slim POC 的
完整传递依赖版本，Python 3.11 `pydanticai-installed` 阻断 job 在与默认依赖联合安装
后执行 `pip check`。这使当前安装兼容窗口可复现，但仍不是两个干净环境的净增量
比较，也没有平台矩阵、resolver report 或 artifact hash；因此不得据此恢复历史包数
或“增量成本较低”结论。量化依赖足迹仍须生成双环境证据再比较。

## 4. 尚未收集的证据（不得冒充完成）

| 缺口 | 需要 | 原因 |
| --- | --- | --- |
| 真实 provider latency（p50/p95）与成本 | CI secret 中的真实 API key | recovery plan 要求真实 benchmark 独立为 network/Actions artifact、不读开发者 ambient 凭据；本地无法产出真实数字 |
| schema/报告成功率、attribution、error classification 的**真实 provider** 表现 | 同上 | 离线 replay 只能证明契约等价，无法反映真实模型行为分布 |
| Desktop（macOS / Windows）安装/启动/卸载/体积 | 多平台构建机 | recovery plan RF-07 要求 Desktop 独立完成多平台真实打包证据 |
| prompt、reasoning/provider trace、完整 tool result、日志/artifact 和其它原始异常失败面 | 按公开面逐项种植 canary 的隔离测试与 artifact 扫描 | 历史 leak scan 只覆盖 provider-error 终端诊断 |
| 可复现依赖净增量 | 两个干净环境的 resolver 输出、lock/report、平台/Python 元数据和 hash | 当前精确传递闭包只固定安装兼容窗口；仍无默认/实验双环境快照，无法量化净增包数 |

在上述证据补齐前，`Continue Experimental` 所需的“明确收益”无法成立。

## 5. 裁决（RF-07）

**维护者 2026-07-18 裁决：`Native Only`。**

- 依据：精确的 Single RUN fixture 子集（3.1）与 provider-error 诊断回归（3.2）
  只提供了部分离线证据；依赖净增量（3.3）、其它泄漏面、真实 provider benchmark
  与 Desktop 多平台打包证据均未完成。证据不足不能支持 `Continue Experimental`，
  因此按既定默认路径裁决 `Native Only`；该裁决不应被表述为 RF-06 全部门禁完成。
- 生效结果：Native Runtime 是唯一可执行 Runtime；实验 PydanticAI Adapter、toolset、可选依赖清单、内部注入点、cross-runtime 测试和专用 CI 已删除。本轮不新增用户设置、环境变量开关、公开 API 或持久 Agent Job。
- 保留资产：Contract（RF-02）、BoundToolSession（RF-03）、统一生命周期/fence（RF-04）等已在 Native 证明价值的架构收益保留，不随实验资产删除而回滚。
- 重启条件：若未来维护者补齐第 4 章证据，必须另立 ADR 并从当前中立 Contract 重新接入；不得直接恢复历史 Adapter 或把 recovery plan 当作现行指令。

## 6. 回滚

- Native Only 实施可通过整体 revert 对应提交回滚；不得只恢复 Adapter、依赖或 CI 的一部分。
- Contract、BoundToolSession、生命周期、事件、sanitizer 和 Native replay 测试不属于实验资产，不随回滚删除。

## 7. 2026-07-19 维护者改判（ADR-002）

RF-07 的 `Native Only` 是 recovery plan 的默认规则结果：`Continue Experimental`
所需证据（真实 provider benchmark、Desktop 多平台打包等）依赖维护者资源，无人
值守流程无法产出，因此按默认路径收尾。2026-07-19 维护者本人裁决改判为
`Continue Experimental`，恢复实验 PydanticAI Runtime 为测试/证据 POC；完整决策见
`docs/architecture/ADR-002-pydanticai-runtime-reinstatement.md`。

改判不改变本报告第 3～5 章的历史记录与证据边界：

- 第 4 章缺口仍未收集，证据状态保持 `Historical / Partial`，不因资产恢复而升级。
- RF-07 当时按默认规则裁决 `Native Only` 的事实保持原样，不重写历史。
- 恢复后的 conformance 以显式 fixture ID 允许清单运行（8 个完全等价 + 3 个仅
  终态分类等价，即第 3.1 节冻结的同一组 ID），未知 `single_run` fixture fail
  closed，符合第 3.1 节"不得按 `profile` 自动扩展"的边界。
- `Continue Experimental` 约束全部生效：Native 永久默认且可零 PydanticAI 依赖
  运行；runtime fallback 默认关闭；本轮不新增用户设置、环境变量开关或公开
  API；实验资产保持整体可删除。
- POC 只允许测试/证据 harness 直接构造，不存在生产 factory/config/env/API
  selector；`start()` 的 live handle、状态锁内原子 cancel/deadline 终态解析、bridge
  与 direct-model tool dispatch/result acceptance reservation、迟到结果审计 fence，
  以及完整精确依赖闭包均由安装态门禁覆盖。
- ADR-002 明确、有限覆盖 ADR-001 D5 的直接恢复禁令；真实 provider、完整泄漏面、
  Desktop 与双环境净增量仍阻断任何产品入口、支持矩阵扩展或默认 Runtime 变更。
