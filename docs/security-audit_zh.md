# 持久安全审计

StockPulse 将特权操作决策以版本化 `security-audit-v1` 合同写入主 SQLite
数据库。该链路独立于应用日志、Agent 运行时事件、Run Diagnostics，以及
#222 跟踪的跨阶段可观测性工作。

人工审批提案创建/复用、状态流转、一次性消费与最终风险旁路授权均使用同一
强制 attempt/completion 服务。元数据仅限提案 id、稳定风险/状态枚举与 CAS
版本。见 [Human-in-the-Loop Approval Safety Gate](human-approvals_EN.md)；
提示词、cookie、凭据、完整模型参数与无界推理不是审批审计字段。

本文是 [#1062](https://github.com/SiinXu/stock-pulse-ai/issues/1062) 的特权
路径覆盖图，不是审计链路的重建说明。Phase 1 存储、脱敏、管理员查询，以及
原始 HTTP/MCP/工具/HITL/插件/本地进程连接已经存在。剩余工作是按 DAG 补齐
覆盖，而不是一次扫全仓库的 mega-PR。

English version: [Durable Security Audit](security-audit.md).

## 事件合同

每条记录为追加写，包含：

- UTC `occurred_at` 与稳定 `event_type`；
- `attempt` 或 `completion` 阶段；
- 有界 actor 与 execution 身份；
- 稳定 action 与有界 target type/id；
- outcome 与 reason code；
- attempt 与 completion 共用的 correlation ID；
- 递归脱敏且大小有界的 metadata。

元数据上限：16 个对象键、列表 64 项、字符串 256 字符、嵌套两层。一般元数据
超界 fail-closed。

系统配置更新可包含超过 64 个动态 Connection 字段，因此使用有界证据而非
请求体大小限制：`key_sample` 为脱敏后排序去重的前 64 个键名；超过 256 字符的
键用 `sha256:<hex>` 表示。`key_count` / `item_count` / `keys_truncated` /
`keys_sha256` 保留完整键集合证据。事件中永不包含配置值。

## 特权路径覆盖图

对照当前 `main`。状态以生产路径上的 `SecurityAuditService` /
`record_attempt` 调用为准，而不是“文件存在即已交付”。
[#1062](https://github.com/SiinXu/stock-pulse-ai/issues/1062) 工作流 A–D
复选框和若干基线缺口行写于 Phase 1 落地之后，相对本图**已过时**。不要把
**已落地** 行再实现一遍。

图例：

| 状态 | 含义 |
| --- | --- |
| **已落地** | 在接受/拒绝边界写入 attempt 与 completion |
| **部分** | 同一特权操作只有部分入口写入 |
| **缺失** | 特权接受/拒绝没有持久安全审计行 |
| **延期** | 不在 #1062 验收范围内，或实现前需要具名负责人 |

### 原始 issue 清单（工作流 A）

| 操作 | `event_type` | 状态 | 负责人 / 说明 |
| --- | --- | --- | --- |
| 登录成功/失败 | `auth.login` | **已落地** | `src/api/v1/endpoints/auth.py` |
| 认证启用/禁用 | `auth.policy` | **已落地** | 同上；AUTH-04 再认证仍在；不存储密码 |
| 登出 / 会话失效 | `auth.logout` | **已落地** | 会话密钥轮转嵌在该路径内 |
| 修改密码 | `auth.password_change` | **已落地** | 成功与拒绝均审计 |
| 敏感配置创建/更新 | `system_config.write` | **部分** | 仅 HTTP `src/api/v1/endpoints/system_config.py`。`SystemConfigService.update` 本身无 recorder；配置预设、onboarding apply、本地模型配置写入会旁路。负责人：DAG-5 |
| 配置导出 | `system_config.export` | **已落地** | 仅版本/字节长度，不含 `.env` 正文 |
| 配置导入 | `system_config.import` | **已落地** | 同上边界 |
| 配置回滚 | `system_config.rollback` | **已落地** | attempt 失败则阻止恢复 |
| 工具允许/拒绝 | `tool.execute` | **已落地** | `src/agent/runtime/tool_session.py`；completion 写失败为 `retriable=false` |
| 分析策略接受/拒绝 | `analysis.submit` | **已落地** | `AnalysisSubmissionService` 与共享 `record_audit`：HTTP 异步 `/analyze`、HTTP **同步** `/analyze`、MCP `trigger_analysis`、事件触发告警、bot `/analyze`、定时任务派发、组合 `analyze_position`。市场复盘 / 候选发现 / AlphaSift 仍是另一套队列 API（不是本事件）。 |
| 审计包 / 证据链导出 | `audit_package.export` / `evidence_chain.export` | **已落地** | `src/api/v1/endpoints/evidence_pack.py`。产品包完整性仍属 [#127](https://github.com/SiinXu/stock-pulse-ai/issues/127)；这不是第二条安全审计落点。见 [证据链审计包](evidence-chain-audit-package_EN.md) |

中文旧表把证据包导出写成“不在范围”，与英文 Connected 表及当前代码不一致；以上行以代码为准。

### 超出原始清单、已落地（不要重做）

| 操作 | `event_type` | 状态 | 负责人 / 说明 |
| --- | --- | --- | --- |
| HITL 提案 / 流转 / 消费 / 规则 | `approval_proposal`, `approval_transition`, `approval_consume`, `approval_rule`, `approval_completion` | **已落地** | [#251](https://github.com/SiinXu/stock-pulse-ai/issues/251) 已于 2026-07-25 关闭。`src/services/approval_service.py`。默认关闭；见 [human-approvals.md](human-approvals.md) |
| 插件加载/启停/热加载 | `plugin.lifecycle` | **已落地** | 管理员变更 fail-closed；**启动**加载为 best-effort，避免单个 recorder 故障阻塞无关插件 |
| MCP 认证 | `mcp.auth` | **已落地** | `src/mcp_server/auth_gate.py`、`src/mcp_server/server.py` |
| MCP 工具列表 / 调用 / 取消 | `mcp.request` | **已落地** | 含 `action=mcp.request.cancel`。HTTP 分析 cancel 是另一条特权停止路径（DAG-3） |
| 本地 OCR / CLI 进程 | `local_process.execute` | **已落地** | 目标为 `local_process.ocr` / `local_process.cli` |
| 能力注册/更新/退役及未认证拒绝 | `capability.write` | **已落地** | `src/capability_registry/write_audit.py`；能力写入**不**在鉴权豁免名单 |
| Research API 结论 | `research_api.request` | **已落地** | `src/api/v1/endpoints/research.py` |
| Research pack 导出 | `research_pack.export` | **已落地** | 返回字节前 fail-closed |
| Reasoning-trace 导出 | `reasoning_trace.export` | **已落地** | 返回字节前 fail-closed |

### 真实剩余特权缺口

| 操作 | 入口 | 状态 | 为何属于 #1062 | 负责人 |
| --- | --- | --- | --- | --- |
| Bot `/analyze` | `src/bot/commands/analyze.py` → `AnalysisSubmissionService.submit`（`query_source="bot"`，actor `bot`/`bot`） | **已落地** | 先 attempt 再入队；request_context 留在任务上，不进入审计 metadata | DAG-1 |
| 定时任务派发 | `src/services/scheduled_task_service.py` → `submit_tasks_batch`（`query_source="scheduled_task"`，actor `scheduler`/`scheduled_task`） | **已落地** | attempt 在入队 fence 前单独提交，避免 SQLite 双重写锁；已拥有执行的 retry 不是新的 `analysis.submit` | DAG-1 |
| 组合持仓分析 | `src/api/v1/endpoints/portfolio.py` `analyze_position`（`query_source="portfolio"`，actor `api_client`/`portfolio_submitter`） | **已落地** | HTTP 分析入队；持仓数量/成本/账户只作为队列 kwargs | DAG-1 |
| HTTP 同步 `/analyze` | `src/api/v1/services/analysis_api_service.py` `handle_sync_analysis` | **已落地** | 与异步共用 `analysis.submit` 合同；`analyze_stock` 前写 attempt，completion 为 `success`/`failure` | DAG-1 |
| 定时任务创建/启用/禁用 | `src/api/v1/endpoints/scheduled_tasks.py` → `ScheduledTaskService.create_task` / `set_enabled` | **已落地** | `scheduled_task.write` 先 attempt 再持久化；HTTP actor 为 `administrator`/`authenticated_admin`/`local_operator`/`desktop_operator`。内部隔离走 `repository.set_enabled`，不是本事件。不存在 PUT/PATCH/DELETE 定义路由 | DAG-2 |
| 分析 HTTP cancel | `src/api/v1/endpoints/analysis.py` `cancel_analysis_task`（路由已随 [#1466](https://github.com/SiinXu/stock-pulse-ai/pull/1466) 进入 `main`） | **缺失** | 停止运行中分析的特权控制。#1466 已落地路由但**不含**安全审计。DAG-3 只补审计，不得改 cancel 线协议 | DAG-3 |
| 报告 Markdown/HTML/PDF 导出 | `src/api/v1/endpoints/report_export.py` | **缺失** | AUDIT-02 导出/受保护数据。可选后续 | DAG-4 |
| 历史删除（按代码 / 按 id） | `src/api/v1/endpoints/history.py` | **缺失** | 受保护数据销毁。可选后续 | DAG-4 |
| 配置预设应用/保存 | `src/services/config_profile_service.py` → `SystemConfigService.update` | **缺失** | 与 HTTP `system_config.write` 同一特权配置变更 | DAG-5 |
| Onboarding apply | `src/services/onboarding_plan_service.py` → `SystemConfigService.update` | **缺失** | 同一未审计配置写入器 | DAG-5 |
| 写入配置的本地模型注册/分配/删除 | `src/services/local_model_service.py` → `SystemConfigService.update` | **缺失** | 运行时模型控制面走同一未审计 updater | DAG-5 |
| 模型包导入 / 桌面激活 | `src/api/v1/endpoints/model_packs.py` | **缺失** | 可信制品安装 | DAG-5 / 具名延期 |
| HTTP 市场复盘 / 候选发现 / AlphaSift | analysis API、`candidate_discovery.py`、`alphasift.py` 的 `submit_background_task` | **缺失** | 另一套队列 API 上的特权后台执行。**不是** DAG-1 | 覆盖图具名行；后续负责人 |
| 投资框架变更 | `src/services/investment_framework_service.py` | **缺失** | 分析策略内容；除非明确视为策略控制，否则延期 | 延期，除非重新归类 |

DAG-1 已扩展 `AnalysisSubmissionCommand`（`query_source`、`request_context`、
`portfolio_context`、`strict_skill_selection` 与 actor 身份），并共享
`record_audit` 以及“先 attempt 再执行受保护操作”的 fail-closed 顺序。HTTP 异步 /
MCP / 事件触发仍使用 `api_client` / `analysis_submitter`。不要把市场复盘、候选
发现或 AlphaSift 折进本事件。

DAG-2 在 `ScheduledTaskService.create_task` 与 `set_enabled`（HTTP 创建/启用/
禁用）写入 `scheduled_task.write`。attempt 在定义写入前提交。metadata 仅含
task_type、schema_version、enabled、schedule_kind、calendar_market、
requested_enabled 与 idempotent，不含 name、payload、密钥或股票代码。调度器
隔离仍走 `repository.set_enabled`，不写本事件。

DAG-5 应在 `SystemConfigService.update` 上审计一次，而不是逐入口打补丁。
已经审计的 HTTP `system_config.write` 路径不得重复写入。

### 延期（不在本 DAG）

| 操作 | 状态 | 原因 |
| --- | --- | --- |
| CLI / GitHub Actions 每日分析（`src/app/analysis.py` / `main.py`） | **延期** | 操作员 TTY / Actions 身份即 actor；不是未信任 API |
| 安全审计查询本身（`GET /api/v1/security/audit-events`） | **延期** | 读取安全记录；#1062 验收未要求自审计 |
| 自选 / 组合 CRUD / 告警 | **延期** | 产品数据，不是原始特权清单；会无界扩大 #1062 |
| 密码学篡改证据（哈希链 / HMAC / WORM） | **延期** | AUDIT-03 要求追加写与访问控制，不是 HSM/WORM。属操作员信任残余限制 |
| SIEM / 批量审计导出 | **延期** | #1062 明确非目标 |
| 多租户 actor | **延期** | [#230](https://github.com/SiinXu/stock-pulse-ai/issues/230) 以 not-planned 关闭；AUTH-05 仍为单管理员 |
| Agent 可观测性追踪 | **延期** | 独立落点，归属 [#222](https://github.com/SiinXu/stock-pulse-ai/issues/222) |
| 替换产品证据包 | **延期** | 明确非目标；产品完整性剩余面是 #127 |

导入导出元数据仅含配置版本、标志与字节长度，不含 `.env` 原文或密钥。本地
进程元数据仅限引擎/预设 id、语言、超时、状态、扩展名与大小——不含图片字节、
prompt、stdout 或密钥。

## 剩余覆盖 DAG

不要把 DAG-1 到 DAG-5 合成一个 PR。不要纳入自选、组合 CRUD 或告警。不要把
市场复盘、候选发现或 AlphaSift 折进 DAG-1。

```text
DAG-0  本覆盖图（仅文档；无运行时行为）
  │
  ├── DAG-1  分析入队（已落地）
  │            bot + 定时任务派发 + 组合 analyze_position
  │            + HTTP 同步 /analyze
  │            保留 query_source / 上下文 kwargs / actor 身份
  │
  ├── DAG-2  定时任务创建/启用/禁用（已落地）
  │            HTTP 创建/启用/禁用；不是派发，也不是隔离
  │            独立于 DAG-1
  │
  ├── DAG-3  分析 HTTP cancel 审计
  │            路由已随 #1466 进入 main；
  │            只补持久审计，不得改 cancel 线协议
  │
  └── DAG-4  报告导出 + 历史删除
               可选 AUDIT-02；独立

DAG-5  SystemConfigService.update 旁路
         （预设 / onboarding / 本地模型配置写入）
         + 若仍标为特权的模型包
         覆盖图现在记为 Missing；在 DAG-1 之后实现；
         服务层一次审计，HTTP 路径不得双写
```

后续建议标题（英文，无工具前缀）：

1. `docs: publish privileged security-audit coverage map for #1062`（DAG-0，已落地）
2. `fix: audit analysis admission on bot scheduler portfolio and sync HTTP paths`（DAG-1，已落地）
3. `feat: emit security-audit events for scheduled-task mutations`（DAG-2，已落地）
4. `feat: audit analysis task cancel at the HTTP boundary`（路由已随 #1466 进入 main）
5. `feat: audit report export and history deletion`

在范围内剩余行变为 **已落地** 或带负责人的 **延期** 之前，保持 #1062 开放。
不要用关闭 #535 代替本覆盖图。

## Issue 与基线卫生

以下是文档事实，不是本页对 GitHub issue 的实际改写：

- 线上 #1062 工作流 A–D 与验收复选框仍全部未勾。原始 A 清单的
  HTTP/MCP/工具/HITL/插件/本地进程路径以及证据包导出已经是 **已落地** 或
  **部分**。后续复选框应只列 DAG-3..5。
- [#251](https://github.com/SiinXu/stock-pulse-ai/issues/251) HITL 门控已关闭
  并写入 `approval_*` 事件。Current Gaps 若仍写“门控缺失”则过时；见
  [security-baseline.md](security-baseline.md)。
- [#535](https://github.com/SiinXu/stock-pulse-ai/issues/535) 是父产品需求。
  剩余**安全审计覆盖**属 #1062。剩余**产品证据包完整性**属 #127。不要把
  证据包导出当成第二条未实现的安全落点。
- [#191](https://github.com/SiinXu/stock-pulse-ai/issues/191) ToolSurface
  沙箱与持久拒绝已落地。工作流 C 工具复选框未勾是 issue 卫生问题，不是缺代码。

## 持久化与脱敏

`SecurityAuditService` 在仓库落库前调用 `src.utils.sanitize` 递归脱敏。仓库仅
提供追加、有界查询、按时间保留与容量上限；无更新或按行删除 API。SQLite 回归
测试证明 token、cookie、密钥字段与带凭据 URL 不会进入表。

## 保留期与容量上界

默认值（通过共享 `Config` / 环境变量覆盖）：

| 配置项 | 环境变量 | 默认 | 范围 |
| --- | --- | --- | --- |
| 时间保留 | `SECURITY_AUDIT_RETENTION_DAYS` | 90 | 1–3650 |
| 容量上界 | `SECURITY_AUDIT_MAX_EVENTS` | 10000 | 100–1000000 |

保留在追加与查询时执行（每个服务/数据库对每个 UTC 日一次）。容量在每次成功
追加后执行，超限时优先删除最旧行。两者独立。需要更长法证保留的运营方须在
删除前另行归档。

## 访问控制

`GET /api/v1/security/audit-events` 支持有界分页与精确 event-type / outcome /
correlation / UTC 时间过滤，需要有效的单管理员会话。认证关闭时返回 `403`
`security_audit_auth_required`，会话缺失/无效返回 `401` `unauthorized`。存储
故障返回 `503` `security_audit_unavailable`。Web 设置中的只读「安全审计」
面板消费同一 API，信任服务端脱敏，并在认证关闭时展示诚实阻断状态。本交付
不含多租户 RBAC、批量导出或 SIEM 集成。

鉴权中间件豁免仅限 login、status、health、scorecard、docs 与 OpenAPI。能力
写入**不**在豁免名单；未认证拒绝会写入 `capability.write` 或 fail-closed
`503`。Actor id 是有界 token（`admin_session`、`unauthenticated`、
`capability_registry`、`analysis_submitter`、`bot`、`scheduled_task`、`portfolio_submitter`、
`authenticated_admin`、`local_operator`、`desktop_operator`），不是邮箱。MCP 能力
`security_audit_admin` 为 `not_exposed`。

内存 outbound-activity 环形缓冲（`GET /api/v1/security/outbound-activity`）
是独立的 NET-06 落点，不是持久 `security_audit_events` 表。

## 篡改与完整性边界

仓库为追加写：仅暴露追加、有界查询、按时间保留与容量删除。无更新或按 id
删除 API。保留与容量**就是**删除（先删最旧行），不是法证冻结归档。

SQLite 文件对操作员可写。本交付没有哈希链、HMAC 或 WORM 设备。#535 历史
评论中的密码学篡改证据**不在** #1062 验收范围内。将其视为操作员信任残余
限制，而不是本 issue 隐藏缺陷。

## 失败语义

受保护路径在执行前写入 attempt。写入失败则 fail-closed，错误码为
`security_audit_unavailable`：不发登录 cookie、不改配置、不调用工具 handler、
不入队分析、MCP 拒绝、管理员插件变更停止、本地 OCR/CLI 进程不启动、
定时任务创建/启用/禁用不落库。
completion 写入失败同样对外可见，禁止静默吞掉。

审计写失败有可见告警路径：服务通过 `log_safe_exception` 记录脱敏错误日志，
API 返回稳定 `503` / `security_audit_unavailable`。运营方应将其视为审计存储
可用性告警。

SQLite 审计写与密码/配置文件、工具副作用、内存任务队列并非原子。completion
失败可能意味着操作已发生但调用方收到 `security_audit_unavailable`；更早的
attempt 仍然持久。不得将缺失 completion 当作无副作用的证明。

插件**启动**加载使用 best-effort 审计写（`required=False`），避免 recorder
故障阻塞无关插件。管理员插件变更与其他特权路径一样 opt-in fail-closed。

## 与 Agent 可观测性 (#222) 的关系

安全审计是与 #222 运行时事件/诊断/追踪**分离的落点**。可共享脱敏与 correlation，
但安全审计行是 SQLite 追加写、有保留与容量、管理员可查询，并在特权接受边界
fail-closed。调试轨迹不能替代安全审计链。

## 回滚

优先前向修复。迁移 `202607240001_security_audit_events` 无降级路径。完整回滚
需停止写入并以匹配对方式恢复应用与数据库备份。切勿删除迁移行或单条审计行
伪装回滚。仅回退 `SECURITY_AUDIT_RETENTION_DAYS` /
`SECURITY_AUDIT_MAX_EVENTS` 只影响后续强制边界，已删除行不可恢复。
