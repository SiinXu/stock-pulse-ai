# 运行时能力清单

`GET /api/v1/capabilities` 提供运行进程当前已知能力的只读观测。它是
issue #221 的清单基础，并不是中央能力注册表：该端点不能注册、解析、授权、
执行能力，也不负责预算或健康检查。

## 所有者与一致性

投影层不维护 provider 或 tool 的重复目录。每个域都读取既有权威所有者：

| 域 | 权威所有者 | 清单记录 |
| --- | --- | --- |
| `data` | 已在服务调用方的进程 manager 所持有的数据源运行时 | 活跃数据源及其声明的方法 |
| `tool` | Agent `ToolRegistry` | 已注册定义、所有者声明的可选成员及 scope |
| `extension` | `PluginManager` 及统一扩展注册表 | 插件生命周期观测和活跃贡献 |
| `skill` | 已安装的 `ApplicationServices` 分析策略目录与声明式 `SkillManager` | 进程内真实加载的插件分析策略与自定义 Skill |
| `pipeline` | 共享管线阶段契约（`PIPELINE_STAGE_NAMES` / `PipelineStageName`） | 已绑定的分析管线阶段；未绑定名称会被显式报告，不会伪造 |

可用性判断只来自运行时真实注册与所有者健康状态，绝不复制静态就绪清单。
当注册表或配置读取失败时，该来源返回 `error` 或 `not_initialized` 及明确
`error_code`，响应为 `partial=true`。清单不会安装替代组合根来伪造成功快照。

每个来源只产生一个稳定快照和 generation；同一来源的所有记录共享
`source_generation` 与 `as_of`。插件生命周期记录与扩展注册记录严格分离：
启用但没有活跃注册的插件不属于可执行能力。

数据来源只做观测：优先读取 `ApplicationServices` 组合根 manager（分析主流程
与股票服务使用的同一实例），其次是进程共享的 Agent 工具 manager，绝不新建
manager。新建的 `DataFetcherManager` 拥有另一个数据源运行时，其活跃注册不服务
于任何调用方。当两者都尚未存在时，数据来源报告为 `not_initialized`，而不是
返回空清单。

扩展与技能来源同样只观测已经安装的组合根。调用清单端点绝不会构造默认
`ApplicationServices`：缺失时报告 `not_initialized`
（`application_services_not_initialized`）。技能配置或目录加载失败分别暴露为
`skill_config_unavailable` 与 `skill_catalog_unavailable`。

工具来源只观测已经构建的进程 `ToolRegistry`，绝不会为了清单去构造它。技能来源 generation 包含插件身份，以及声明式技能所有记录可见字段（`name`、`source`、`enabled`、`display_name`、`required_tools`）的有界规范哈希，因此同名技能元数据变化和等数量目录替换都会推进 generation。管线阶段只有在 live `StockAnalysisPipeline` 暴露 stage runner 且已绑定方法引用该阶段时才算 bound；仅注册不会把 `healthy` 设为 `true`。

所有者 generation 覆盖记录可暴露的每一处变化。工具条目是注册时捕获的冻结
副本，因此事后原地修改活跃 `ToolDefinition` 不会改变已发布清单；真实变更必须
经过注册并推进 generation。插件生命周期迁移会推进独立的生命周期计数器并计入
已发布的扩展 generation，因为生命周期迁移不会触碰扩展注册 generation。

若权威所有者读取失败，端点返回 `200`、`partial=true`、明确的来源状态
（`error`、`generation_drift` 或 `not_initialized`），并且不会为该来源伪造
记录。消费者不能把失败来源中缺失的记录解释为“已禁用”或“未注册”。

## 状态语义

schema 版本为 `capability-inventory/v1`。各状态彼此独立：

- `registered`：已在权威所有者中观测到。
- `configured`：已知所需配置是否存在。
- `dependency_ready`：已知运行依赖是否就绪。
- `grantable`：当前 ToolSurface/安全上下文是否可授权。
- `executable`：当前是否已知可以执行。
- `healthy` 与 `degraded`：所有者提供时的实时运行健康状态。

除所有者直接提供的事实外，就绪状态保持 `null`；“已注册”不代表已配置、
已授权、可执行、预算允许或健康。插件生命周期记录固定为
`executable=false` 且 `reason_code=lifecycle_not_capability`，因为生命周期是
诊断信息，不是插件贡献的能力。

`reason_code` 记录所有者对可选工具缺失的真实解释：`feature_disabled` 与
`missing_config` 描述配置层，`construction_failed` 与
`construction_produced_no_tool` 描述已配置但抛错或未产出工具的构造过程。
只有当所有者未提供任何理由时才使用 `not_registered`，因此依赖失败不会被降级
成普通缺失。

所有者身份不会被压成单个标量。`provider` 表示唯一归属身份，`providers` 列出
供给该能力的全部身份，`provider_count` 是真实供给数量。因此由多个数据源共同
提供的方法不会撑爆有界字段，也不会把正常来源变成错误来源。若数量超过列表上
限，则报告已列出的子集并附带 `reason_code=provider_list_truncated`，同时保留
真实总数。

## 请求与响应

可重复使用 `domain` 参数选择来源：

```http
GET /api/v1/capabilities?domain=data&domain=tool
```

响应字段与完整示例见英文文档
[`capability-inventory.md`](capability-inventory.md)。计数字段把 `executable`
明确分为 `true`、`false`、`null` 三组，避免把未知状态折叠成不可用。

未知 domain 返回 `400`。当 `ADMIN_AUTH_ENABLED=true` 时，生产应用要求有效的
已签名管理员 session cookie；缺失或无效 session 使用标准 `401 unauthorized`
错误信封拒绝。

## 扩展示例与兼容性

当已启用插件在 `agent_tool` 扩展点贡献 `demo_tool` 注册时，清单新增类似
`extension.registration:agent_tool:demo_tool` 的 `extension_registration` 记录。
其 `version` 是扩展合同版本，`provider` 是插件 ID，`dependencies` 包含扩展点。
插件管理器会在注册生效前执行既有兼容性检查；本清单不会再做一套重复判断。

消费者必须根据 `schema_version` 分支，容忍新增记录和可空状态，并把来源错误
视为未知。


## 写入侧注册表（控制面）

在只读清单之外，进程还提供持久化的**写入侧**能力控制面（schema
`capability-write-registry/v1`），用于操作员声明式元数据、依赖解析与任务感知
路由。它**不会**替换 live owner：此处登记本身不会把工具、插件或模型安装进执行路径。

| 操作 | 端点 | 说明 |
| --- | --- | --- |
| 列出声明 | `GET /api/v1/capabilities/registry` | 可选 `domain`、`include_retired` |
| 登记 | `POST /api/v1/capabilities/registry` | 特权操作；必须走安全审计 attempt/completion |
| 更新 | `PUT /api/v1/capabilities/registry/{capability_id}` | 身份字段不可变 |
| 下线 | `POST /api/v1/capabilities/registry/{capability_id}/retire` | 已下线 id 幂等成功 |
| 依赖解析 | `POST /api/v1/capabilities/resolve` | fail-closed 的 ready 与 reason_code |
| 任务路由 | `POST /api/v1/capabilities/route` | 可解释决策，便于诊断追溯 |

写入域：`data`、`tool`、`skill`、`pipeline`、`llm`、`persona`。

硬性规则：

- 变更必须经过特权操作审计链（`event_type=capability.write`）。审计不可用时返回
  `503` / `security_audit_unavailable`，**不会**落盘写入。
- 校验失败、身份冲突、存储损坏返回明确错误码；注册失败绝不能伪造成功快照。
- 默认存储路径为
  `<DATABASE_PATH 目录>/capability_write_registry.json`
  （可用 `CAPABILITY_WRITE_REGISTRY_PATH` 覆盖）。损坏文件 fail-closed。

### 依赖与兼容性解析

`POST /api/v1/capabilities/resolve` 对照写入注册表与可选 live 清单评估依赖。
支持的依赖 token：`capability_id`、`@`/`==` 精确、`>=`、`~=`。

缺失、已下线、不可执行或版本不兼容时返回 `ready=false` 与明确 `reason_code`
（绝不 fail-open 成 ready）。

### 任务感知模型路由

`POST /api/v1/capabilities/route` 返回版本化 `task-route-decision/v1` 决策。
手动钉选始终优先；`TASK_ROUTING_ENABLED=true` 时按标签与
`TASK_ROUTING_POLICY`（`quality` | `cost` | `local_first`）打分。

可选 multi-model ensemble 不在本切片内，仍由 issue #204 跟踪。

## 仍开放（issues #221 / #204）

- 每个执行路径上的 ToolSurface 授权/预算策略强制
- 启动/启用/热重载路径上把全部扩展类迁移到写入侧契约
- 能力安装/启用/治理的产品 UI
- 可选、有预算上限的 ensemble/vote 模式

