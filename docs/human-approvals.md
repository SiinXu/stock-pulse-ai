# 人工审批安全门禁

Human-in-the-Loop（HITL）审批为现有 Agent 风控覆写提供一个默认关闭、一次性、可审计的例外路径。它只处理 `risk_control_bypass`：当现有 `risk_veto` 或 `risk_downgrade` 本应把最终建议调得更保守时，管理员可以在短时间内批准保留原始建议。它不是交易审批，不会连接券商、下单或扩大 Agent 工具权限。

## 安全边界

- 当前身份模型仍是本地单管理员，owner 固定为 `local_admin`。审批 API 要求 `ADMIN_AUTH_ENABLED=true` 且请求持有有效管理员 session；认证关闭时返回 `403`，无效或缺失 session 返回 `401`。
- 规则默认关闭。启用后默认有效期为 300 秒，可配置范围为 30–3600 秒；风险来源只能从现有 `risk_veto`、`risk_downgrade` 中选择。
- 提案状态只允许 `pending → approved | rejected | expired | cancelled`。终态不可逆，版本号单调增加；决策使用 `expected_version` CAS，重复相同决策是幂等读取，不会再次变更状态。
- 每个执行输入生成唯一 SHA-256 幂等键；同一次执行和同一份有界上下文会复用原提案。提案持久化后可跨进程重启继续等待并最终过期。
- 只有同 owner、尚未到期、状态为 `approved`、`consumed_at` 为空且版本匹配的提案才能通过一次 CAS 消费。第二个 worker、旧版本、跨 owner、已过期或已消费的请求都不能保留原始建议。
- 创建/复用提案、状态转换、消费和最终授权完成都通过 `SecurityAuditService` 记录 attempt/completion。规则变更和显式决策归因于 `administrator/local_admin`；worker 创建提案、自动过期、消费和完成归因于 `runtime_principal/approval_worker`。审计元数据仅包含稳定枚举、版本和提案标识，不包含 prompt、cookie、凭证、完整模型参数或无界 reasoning。
- 审批存储、审计、轮询、并发或未知错误一律 fail closed：执行现有保守风控覆写。审批失败不会使分析任务绕过风控。

## API

所有路径位于 `/api/v1/approvals`：

| Method | Path | Contract |
| --- | --- | --- |
| `GET` | `/rules/risk-control-bypass` | 读取默认或持久规则 |
| `PUT` | `/rules/risk-control-bypass` | 使用 `expected_version` 更新开关、风险来源和有效期 |
| `GET` | `/` | 按 `status` 分页列出当前 owner 提案 |
| `GET` | `/{id}` | 读取当前 owner 的单个提案 |
| `POST` | `/{id}/decision` | 提交 `approved`、`rejected` 或 `cancelled` 及 `expected_version` |

提案响应只返回 `id`、owner、状态、版本、到期时间、消费时间和有界脱敏上下文。上下文包含股票代码、原始信号、保守信号、稳定风险来源和最多 240 字符的固定风险摘要。版本冲突和非法终态转换返回 `409`；跨 owner 与不存在提案均返回 `404`，避免暴露其他 owner 的存在性。

Web 页面位于 `/approvals`，从 Home 的“待办”卡片进入，不新增一级导航域。页面显示待审批/终态、倒计时、原始与保守信号、批准/拒绝控件，以及最小规则设置。重复点击会被本地禁用；`409` 后页面自动刷新服务器状态。

## 执行语义

唯一门禁位于 `AgentOrchestrator._apply_risk_override`。只有既有风险计划确实 `will_apply` 时才查询规则。规则关闭或风险来源未选中时，行为与历史版本相同。规则命中时 worker 创建或复用提案并轮询；Web/API 可以异步决策：

1. `approved` 且 CAS 消费成功：保留原始、更激进的建议，并在内部 runtime facts 中记录已消费的 proposal id。
2. `rejected`、`cancelled`、`expired`、缺失、失效、跨 owner、重复消费、审计失败或并发失败：应用原有保守建议。
3. worker 重启不会把持久 `pending` 视作授权；只有后续明确批准并由当前执行成功消费才允许绕过。

## 数据迁移与回滚

正式 migration `202607250001_approval_gate_schema` 创建：

- `approval_rules`：owner/action 唯一规则、风险来源 JSON、有效期和 CAS 版本。
- `approval_proposals`：提案状态、唯一幂等键、执行标识、有界上下文、期限、决策时间和一次性消费时间；owner/status/expiry 有联合索引。

迁移是 forward-only 且幂等，并对残缺或同名仿冒存储 fail closed；启动时会验证列名与顺序、SQLite 类型 affinity、非空约束、主键与唯一键、查询索引、DDL 子句、表选项、无外键约束，以及两张目标表和全部目标索引的完整对象清单。部署前应备份 SQLite 数据库。应用回滚的安全步骤是先关闭审批规则，再部署旧代码；新增表可保留且不会被旧代码读取。若必须回滚 schema，应停止写入、恢复 migration 前备份并部署匹配旧版本。不要手工删除 `schema_migrations` 记录。

本功能不实现实盘交易、多级企业 IAM、分布式工作流引擎、Issue #199 的其他人机协作面或 Issue #450 的自我改进能力。
