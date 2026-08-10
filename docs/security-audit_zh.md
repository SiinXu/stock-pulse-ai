# 持久安全审计

StockPulse 将特权操作决策以版本化 `security-audit-v1` 合同写入主 SQLite
数据库。该链路独立于应用日志、Agent 运行时事件、Run Diagnostics，以及
#222 跟踪的跨阶段可观测性工作。

人工审批提案创建/复用、状态流转、一次性消费与最终风险旁路授权均使用同一
强制 attempt/completion 服务。元数据仅限提案 id、稳定风险/状态枚举与 CAS
版本。见 [Human-in-the-Loop Approval Safety Gate](human-approvals_EN.md)；
提示词、cookie、凭据、完整模型参数与无界推理不是审批审计字段。

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

## 已连接的特权路径

| 操作 | `event_type` | 状态 |
| --- | --- | --- |
| 登录成功/失败 | `auth.login` | 已连接 |
| 认证启用/禁用 | `auth.policy` | 已连接 |
| 登出 / 会话失效 | `auth.logout` | 已连接 |
| 修改密码 | `auth.password_change` | 已连接 |
| 系统配置写入 | `system_config.write` | 已连接 |
| 配置导出 | `system_config.export` | 已连接 |
| 配置导入 | `system_config.import` | 已连接 |
| 配置回滚 | `system_config.rollback` | 已连接 |
| 工具允许/拒绝 | `tool.execute` | 已连接 |
| 分析接受/拒绝 | `analysis.submit` | 已连接 |
| HITL 提案/流转/消费 | `approval_*` | 已连接 |
| 插件加载/启停/热加载 | `plugin.lifecycle` | 已连接 |
| MCP 认证 / 工具列表 / 调用 / 取消 | `mcp.auth` / `mcp.request` | 已连接 |
| 本地 OCR 接受/拒绝 | `local_process.execute` (`local_process.ocr`) | 已连接 |
| 本地 CLI 子进程接受/拒绝 | `local_process.execute` (`local_process.cli`) | 已连接 |
| 分析证据包导出 (#127) | — | 不在范围（独立产品） |

导入导出元数据仅含配置版本、标志与字节长度，不含 `.env` 原文或密钥。本地
进程元数据仅限引擎/预设 id、语言、超时、状态、扩展名与大小——不含图片字节、
prompt、stdout 或密钥。

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
correlation / UTC 时间过滤，需要有效的单管理员会话。认证关闭时返回 `403`，
会话缺失/无效返回 `401`。Web 设置中的只读「安全审计」面板消费同一 API。本
交付不含多租户 RBAC、批量导出或 SIEM 集成。

## 失败语义

受保护路径在执行前写入 attempt。写入失败则 fail-closed，错误码为
`security_audit_unavailable`：不发登录 cookie、不改配置、不调用工具 handler、
不入队分析、MCP 拒绝、管理员插件变更停止、本地 OCR/CLI 进程不启动。
completion 写入失败同样对外可见，禁止静默吞掉。

审计写失败有可见告警路径：服务通过 `log_safe_exception` 记录脱敏错误日志，
API 返回稳定 `503` / `security_audit_unavailable`。运营方应将其视为审计存储
可用性告警。

SQLite 审计写与密码/配置文件、工具副作用、内存任务队列并非原子。completion
失败可能意味着操作已发生但调用方收到 `security_audit_unavailable`；更早的
attempt 仍然持久。不得将缺失 completion 当作无副作用的证明。

## 与 Agent 可观测性 (#222) 的关系

安全审计是与 #222 运行时事件/诊断/追踪**分离的落点**。可共享脱敏与 correlation，
但安全审计行是 SQLite 追加写、有保留与容量、管理员可查询，并在特权接受边界
fail-closed。调试轨迹不能替代安全审计链。

## 回滚

优先前向修复。迁移 `202607240001_security_audit_events` 无降级路径。完整回滚
需停止写入并以匹配对方式恢复应用与数据库备份。切勿删除迁移行或单条审计行
伪装回滚。仅回退 `SECURITY_AUDIT_RETENTION_DAYS` /
`SECURITY_AUDIT_MAX_EVENTS` 只影响后续强制边界，已删除行不可恢复。
