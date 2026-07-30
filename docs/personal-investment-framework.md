# 个人投资框架后端合同

[中文](personal-investment-framework.md) | [English](personal-investment-framework_EN.md)

## 当前范围（产品叙事冻结）

Issue #465 以**后端**切片起步。当前 `main` 已有**部分**分析注入与 Settings 最小编辑器。对外叙事必须与代码树一致：

**已交付：**

- 本地版本化存储、CRUD/历史 API、乐观并发
- 稳定的 `InvestmentFrameworkContextReader` 只读 adapter
- **Settings → Agent 行为** 结构化编辑器：创建、版本化保存、停用、删除，以及决策树、评估维度和不可变历史检查
- **个股分析路径**注入：active 框架经 `inject_framework_into_analysis_context`（`src/core/stages/analysis_stock.py` → analyzer 的 `personal_investment_framework_prompt`）作为**只读研究上下文**
- 报告分层 **对齐槽位填充**：有 active 框架时由 `enrich_dashboard_framework_alignment` 写入；否则 `framework_alignment.status=not_configured` 与本地化空槽摘要

**未交付 / 非完整产品：**

- 无导入/导出、无自动交易
- 未作为通用字段接入 Multi-agent / Research / Chat 或 `AnalysisContextPack`
- 注入仅为研究上下文——**不是**实盘交易权限，也**不保证**模型逐条遵守规则

`framework_alignment.status=not_configured` 表示**没有 active 框架**（未创建或已停用）。这是预期空槽，不是分析失败或 bug。

## 账户与权限边界

当前产品只有可选的单一管理员会话，没有可作为授权主体的 user/tenant principal。框架因此固定在服务端 `local` scope：API 不接受 `owner_id`、`user_id` 或 tenant 字段，不能由客户端选择其他身份。`ADMIN_AUTH_ENABLED=true` 时，该 API 与其他 `/api/v1/*` 路径一样需要有效管理员 session cookie；关闭认证时沿用现有本机部署语义。本阶段不提前实现 #230 的多租户账户或 RBAC。

## 内容 Schema

每个版本保存一份严格的 `InvestmentFrameworkContent`：

- `schema_version`：持久化内容合同版本，当前为 `investment-framework-content-v1`；请求省略时使用当前版本。
- `title`：框架名称。
- `description`：可选说明。
- `root_node_id` + `decision_tree`：以稳定 node ID 和 branch target 表示的决策树；terminal branch 使用 `outcome`。
- `evaluation_dimensions`：名称、相对权重、criteria 和可选说明。
- `risk_rules`：明确的风险/仓位规则。
- `tracking_criteria`：持续跟踪条件。
- `free_form_rules`：无法结构化表达的补充规则。

未知字段和标量类型强制转换都会被拒绝，例如 JSON body 中的字符串 `"1"` 不能代替整数 revision，字符串 `"25"` 不能代替数值 weight；响应 DTO 同样不会掩盖服务层类型漂移。`DELETE` 的 revision 仍按 HTTP query 参数的既有 typed parsing 规则处理。该严格边界同样用于持久化内容读取，旧数据中的类型漂移或未知 `schema_version` 会 fail closed，而不会在读取时被静默转换。框架必须至少包含一种实际 criteria；树引用必须指向已声明 node，所有 node 必须从 root 可达且不能形成环，node ID 和维度名称必须唯一。维度名称唯一性使用固定的 Unicode 15.0 默认完整 casefold（`C+F`、非 Turkic）契约；后端和 Web 均使用仓库内固定映射，不依赖 Python、浏览器或 Node 的 Unicode/ICU 版本，重复错误会同时定位到所有相关维度名称字段。权重范围是 `0..100` 的相对权重，本阶段不强制总和等于 100。

## 存储与版本语义

Migration `202607240003_investment_framework_schema` 新增：

- `investment_frameworks`：local aggregate、`latest_version`、可空 `active_version`、独立单调递增 `revision` 和时间戳。
- `investment_framework_versions`：不可变 content JSON、version、change summary 和创建时间；`(framework_id, version)` 唯一。

创建时 `version=1`、`active_version=1`、`revision=1`。每次 `PUT` 都创建新版本并使它 active；不会原地改写历史。停用只清空 `active_version` 并递增 revision，历史仍可读取；停用状态下再次 `PUT` 会创建新版本并重新激活。框架已经停用时，只有携带**当前** `expected_revision` 的重复停用才是幂等 no-op；使用第一次停用前的旧 revision 重试仍返回 `409`，不会绕过乐观并发保护。

每次读取和 mutation 都会在同一 repository session 内验证完整 aggregate：只能有一个 `local` aggregate，版本必须由 1 到 `latest_version` 连续且全部归属该 aggregate，`active_version` 必须为空或等于 latest，并且所有历史内容和 change summary 都必须通过严格解码。可达 revision 状态有明确边界：latest version 为 `N` 时，active aggregate 必须满足 `N <= revision <= 2N-1`，inactive aggregate 必须满足 `N+1 <= revision <= 2N`。验证会先把实际历史行数与持久化 counter 比较，再枚举实际行；损坏的超大 counter 不会触发与其声明值成比例的合成 range 分配。孤儿/外部 owner 版本、缺口、未来版本、不可能的 revision/active 组合、畸形时间戳、过深嵌套或其他损坏内容、无效 change summary 都会 fail closed 为 data error；这些损坏不能被 create/delete 掩盖，也不能被 context reader 当作“未配置”。

Create、update 或 deactivate flush 后，repository 会使 ORM identity state 过期、重新读取持久化行，并在 commit 前证明请求的 aggregate transition 与完整不可变历史 fingerprint 完全一致。若数据库 trigger 或其他 write-side 行为改变了请求内容、counter、active 状态、summary、timestamp 或旧版本，整笔 transaction 都会回滚；响应只从重新读取的持久化状态序列化。

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

所有 mutation 的 `expected_revision` 都针对 aggregate state，而不是 content version。只有确证的 revision 漂移返回稳定 `409 investment_framework_revision_conflict`，`params.current_revision` 告知客户端刷新后重试；version-history constraint 不一致会 fail closed 为服务端 data error，不能伪装成可重试的 revision conflict。不存在返回 `404 investment_framework_not_found`，请求 schema 错误返回现有稳定 `422 validation_error` envelope。

历史端点当前一次返回完整历史，不提供分页。该行为保持本切片的简单合同，但长期频繁更新会使读取成本和响应体随版本数增长；引入分页时必须另行定义兼容的顺序、游标和 total 语义。

## Web 编辑入口

Settings → **Agent 行为 → 投资框架** 横向 Tab 提供独立的页内结构化编辑器和框架状态：

- 创建本机唯一框架（`POST /api/v1/investment-framework`）
- 保存时携带 `expected_revision` 创建新版本并激活（`PUT`）
- 停用（`POST .../deactivate`）后分析不再注入框架
- 删除（`DELETE`）会移除 aggregate 与全部历史
- 读取按版本降序排列的不可变历史；历史详情只读，可复制到草稿后以当前 revision 保存为新版本

**历史版本** 会在同一页面打开只读抽屉，按版本倒序展示不可变历史及当前激活状态。用户可以将任一历史版本复制到当前草稿，再使用 aggregate 的当前 `revision` 保存为一个新版本；复制操作本身不会修改历史或激活状态。

编辑器支持标题、说明、自由规则、按行填写的风险规则/跟踪条件，以及决策树的根节点、节点 ID、问题、条件分支、目标/终局和评估维度的名称、权重、说明、标准。保存前会检查 ID/名称唯一性、目标有效性、根节点、可达性、循环与 `0..100` 权重，并镜像后端数量边界：最多 100 个节点、每节点 20 个分支、50 个维度、每维度 30 条标准、100 条风险规则和 100 条跟踪条件。节点问题、分支条件/终局、维度标准、风险规则和跟踪条件均为每条 1–1000 字符；标题、说明、维度名称与自由规则仍分别遵守 schema 的独立上限。按行字段在输入期间保留末尾换行等编辑草稿，失焦或保存时再规范为去空白的非空列表。重命名节点会以开始编辑时的节点身份同步原有根节点和入站分支引用，即使临时输入了另一个已有 ID，也不会窃取该节点的引用；仍被根节点或入站分支引用的节点不能删除，并会显示本地化依赖。

历史列表和只读检查器都会展示版本 `created_at`；列表会独立标注 latest version 和 active version，因此停用后仍能识别最新快照。历史版本不会原地恢复或修改。“复制到当前草稿”只复制内容，后续保存仍携带当前 aggregate revision 并创建新版本。修订冲突（HTTP 409）不会自动覆盖草稿；页面明确提示冲突，只有用户选择“载入服务器最新版本”时才替换当前草稿。若显式刷新失败，页面隐藏旧草稿并显示可重试的加载错误，避免继续编辑过期内容。后端 422 校验仍是最终权威；重复节点、未知目标、循环、不可达节点和重复维度会返回稳定的 `investment_framework_*` 类型及字段级 `details.issues[].loc`，Web 将这些公开且已脱敏的位置映射到对应节点或维度，并同时保留本地化全局错误提示。未知服务端诊断只保留在错误详情中，不会作为产品主文案显示。编辑已知字段时使用对象合并，并在传输边界保留未知的未来字段，避免滚动升级期间静默丢失服务器所有内容。

页面固定展示研究用途免责声明：不构成投资建议。

## 分析注入路径

股票分析 pipeline（`src/core/stages/analysis_stock.py`，Single 决策仪表盘路径）在增强上下文中：

1. 调用 `inject_framework_into_analysis_context` 读取 active framework。
2. 未配置或停用时 **fail soft**，分析行为与后端切片前一致。
3. 已激活时写入 `personal_investment_framework_prompt` 与序列化 snapshot；`GeminiAnalyzer` prompt 格式化会追加该只读章节。
4. 解析成功后的 dashboard 会通过 `enrich_dashboard_framework_alignment` 填充报告 strata 的 `framework_alignment`（默认 `partial` + 框架标题/版本；若模型已给出 `aligned`/`conflict` 则保留）。

实现入口：`src/services/investment_framework_prompt.py` 与既有 `InvestmentFrameworkContextReader`。

## 分析上下文读取边界

`src.services.investment_framework_context.InvestmentFrameworkContextReader.read()` 返回：

- active framework 存在时：顶层 frozen 的 `investment-framework-context-v1` 只读 adapter payload，包含 framework ID、content version、严格 content 和更新时间。嵌套 content 是从持久化 JSON 解码出的 detached snapshot；调用方在内存中的修改不会写回数据库，但不应把它当作深度不可变对象。
- 未创建或已停用时：`None`，现有分析路径不做任何变化。
- 持久化内容损坏时：fail closed 抛出 data error，不把损坏误报成“未配置”。

个股分析管线经 `src/services/investment_framework_prompt.py` 软失败地加载该 reader。它**不是**通用 `AnalysisContextPack` 字段，也**未**以同样方式接入 Multi-agent / Research / Chat。后续扩展须在其余路径统一优先级、上下文大小、报告披露与回归测试。有 active 框架时，不得描述为实盘交易权限或“模型已保证遵守全部规则”。

## 迁移与回滚

Fresh 数据库由 SQLAlchemy metadata 建表，registered migration 验证 shape 后记录 applied row；受支持 legacy 数据库在同一启动事务中得到等价表。Migration 直接执行也会幂等创建并验证两张表，包括有序列名、SQLite affinity、nullability、default、primary key、精确 unique constraint、foreign key，以及会改变语义的 DDL token。验证固定读取 `main` schema，并要求完整 canonical object inventory：两张目标表、每张表恰好一个预期的 SQLite unique-constraint autoindex、aggregate 表没有 foreign key，且目标表不存在 TEMP object、trigger 或显式 index。带有额外 conflict policy、重复 constraint、`AUTOINCREMENT`、`CHECK`、`COLLATE`、`MATCH`、`DEFERRABLE`、generated-column、辅助 schema object 等隐藏语义的同名 lookalike/shadow，会与类型或约束漂移一样 fail closed，不写 applied row。DDL、验证和 applied row 任一步失败时整笔事务回滚，不留下半张表或伪 applied 状态。

生产 migration 是 forward-only：

1. 升级前停止写入并备份数据库。
2. 若只需停止框架影响，先调用 deactivate，使个股分析注入变为 no-op，分层槽位回到 `not_configured`。
3. 若必须回滚应用与 schema，停止新客户端写入，恢复 migration 前数据库备份，并同时部署匹配的旧代码。
4. 不要手工删除 `schema_migrations` 记录或直接删表伪造降级；旧代码看到未知更高 migration 会按现有合同 fail closed。

回滚 PR 代码但保留新 migration 数据库并不是支持的旧版本恢复方式。若保留当前或更高版本代码，新增空表本身不会改变没有框架时的分析行为。
