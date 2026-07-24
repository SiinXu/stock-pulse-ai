# 个人投资框架后端合同

[中文](personal-investment-framework.md) | [English](personal-investment-framework_EN.md)

## 当前范围

本阶段只交付 Issue #465 的后端切片：单机账户的版本化存储、CRUD/历史 API、乐观并发控制，以及供后续分析装配读取的稳定 adapter。当前版本**不包含**完整 Web 页面、导入/导出、自动交易，也没有把框架真实注入 Single / Multi / Research prompt 或报告。调用 `InvestmentFrameworkContextReader` 只代表读取边界稳定，不能据此宣称 Agent 已遵循个人框架。

## 账户与权限边界

当前产品只有可选的单一管理员会话，没有可作为授权主体的 user/tenant principal。框架因此固定在服务端 `local` scope：API 不接受 `owner_id`、`user_id` 或 tenant 字段，不能由客户端选择其他身份。`ADMIN_AUTH_ENABLED=true` 时，该 API 与其他 `/api/v1/*` 路径一样需要有效管理员 session cookie；关闭认证时沿用现有本机部署语义。本阶段不提前实现 #230 的多租户账户或 RBAC。

## 内容 Schema

每个版本保存一份严格的 `InvestmentFrameworkContent`：

- `title`：框架名称。
- `description`：可选说明。
- `root_node_id` + `decision_tree`：以稳定 node ID 和 branch target 表示的决策树；terminal branch 使用 `outcome`。
- `evaluation_dimensions`：名称、相对权重、criteria 和可选说明。
- `risk_rules`：明确的风险/仓位规则。
- `tracking_criteria`：持续跟踪条件。
- `free_form_rules`：无法结构化表达的补充规则。

未知字段会被拒绝。框架必须至少包含一种实际 criteria；树引用必须指向已声明 node，所有 node 必须从 root 可达且不能形成环，node ID 和维度名称必须唯一。权重范围是 `0..100` 的相对权重，本阶段不强制总和等于 100。

## 存储与版本语义

Migration `202607240002_investment_framework_schema` 新增：

- `investment_frameworks`：local aggregate、`latest_version`、可空 `active_version`、独立单调递增 `revision` 和时间戳。
- `investment_framework_versions`：不可变 content JSON、version、change summary 和创建时间；`(framework_id, version)` 唯一。

创建时 `version=1`、`active_version=1`、`revision=1`。每次 `PUT` 都创建新版本并使它 active；不会原地改写历史。停用只清空 `active_version` 并递增 revision，历史仍可读取；停用状态下再次 `PUT` 会创建新版本并重新激活。重复停用是幂等 no-op，不再次递增 revision。

`DELETE` 与停用不同：它在 revision guard 下删除 aggregate 及所有历史版本，之后可以重新从 version 1 创建。删除不可逆；需要保留历史时必须使用 deactivate。

## API

| Method | Path | Contract |
| --- | --- | --- |
| `POST` | `/api/v1/investment-framework` | 创建 local framework；已存在返回 `409` |
| `GET` | `/api/v1/investment-framework` | 读取 latest version；inactive 时仍返回内容并令 `is_active=false` |
| `PUT` | `/api/v1/investment-framework` | 携带 `expected_revision` 创建并激活新版本 |
| `GET` | `/api/v1/investment-framework/history` | 按 version 降序读取完整不可变历史 |
| `POST` | `/api/v1/investment-framework/deactivate` | 携带 `expected_revision` 停用，保留历史 |
| `DELETE` | `/api/v1/investment-framework?expected_revision=N` | 删除 aggregate 与全部历史 |

所有 mutation 的 `expected_revision` 都针对 aggregate state，而不是 content version。旧 revision 返回稳定 `409 investment_framework_revision_conflict`，`params.current_revision` 告知客户端刷新后重试。不存在返回 `404 investment_framework_not_found`，请求 schema 错误返回现有稳定 `422 validation_error` envelope。

## 分析上下文读取边界

`src.services.investment_framework_context.InvestmentFrameworkContextReader.read()` 返回：

- active framework 存在时：不可变 `investment-framework-context-v1` payload，包含 framework ID、content version、严格 content 和更新时间。
- 未创建或已停用时：`None`，现有分析路径不做任何变化。
- 持久化内容损坏时：fail closed 抛出 data error，不把损坏误报成“未配置”。

该 reader 目前没有接入 `AnalysisContextPack` 或 Agent prompt。后续真实接线必须在 Single / Multi / Research 各装配入口统一处理优先级、上下文大小、报告披露和回归测试。

## 迁移与回滚

Fresh 数据库由 SQLAlchemy metadata 建表，registered migration 验证 shape 后记录 applied row；受支持 legacy 数据库在同一启动事务中得到等价表。Migration 直接执行也会幂等创建并验证两张表。DDL、验证和 applied row 任一步失败时整笔事务回滚，不留下半张表或伪 applied 状态。

生产 migration 是 forward-only：

1. 升级前停止写入并备份数据库。
2. 若只需停止框架影响，先调用 deactivate；当前分析本来就没有 prompt 注入。
3. 若必须回滚应用与 schema，停止新客户端写入，恢复 migration 前数据库备份，并同时部署匹配的旧代码。
4. 不要手工删除 `schema_migrations` 记录或直接删表伪造降级；旧代码看到未知更高 migration 会按现有合同 fail closed。

回滚 PR 代码但保留新 migration 数据库并不是支持的旧版本恢复方式。若保留当前或更高版本代码，新增空表本身不会改变没有框架时的分析行为。
