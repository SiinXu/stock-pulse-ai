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

每个来源只产生一个稳定快照和 generation；同一来源的所有记录共享
`source_generation` 与 `as_of`。插件生命周期记录与扩展注册记录严格分离：
启用但没有活跃注册的插件不属于可执行能力。

数据来源只做观测：优先读取 `ApplicationServices` 组合根 manager（分析主流程
与股票服务使用的同一实例），其次是进程共享的 Agent 工具 manager，绝不新建
manager。新建的 `DataFetcherManager` 拥有另一个数据源运行时，其活跃注册不服务
于任何调用方。当两者都尚未存在时，数据来源报告为 `not_initialized`，而不是
返回空清单。

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
视为未知。中央写入注册、依赖解析、Stage/Skill/LLM/Persona 元数据、ToolSurface
授权与预算评估、启动校验和迁移仍不属于该 API，继续由 issue #221 跟踪。
