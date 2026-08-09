# 运行时能力清单

`GET /api/v1/capabilities` 提供运行进程当前已知能力的只读观测。它是
issue #221 的清单基础，并不是中央能力注册表：该端点不能注册、解析、授权、
执行能力，也不负责预算或健康检查。

## 所有者与一致性

投影层不维护 provider 或 tool 的重复目录。每个域都读取既有权威所有者：

| 域 | 权威所有者 | 清单记录 |
| --- | --- | --- |
| `data` | manager 持有的数据源运行时 | 活跃数据源及其声明的方法 |
| `tool` | Agent `ToolRegistry` | 已注册定义、所有者声明的可选成员及 scope |
| `extension` | `PluginManager` 及统一扩展注册表 | 插件生命周期观测和活跃贡献 |

每个来源只产生一个稳定快照和 generation；同一来源的所有记录共享
`source_generation` 与 `as_of`。插件生命周期记录与扩展注册记录严格分离：
启用但没有活跃注册的插件不属于可执行能力。

若权威所有者读取失败，端点返回 `200`、`partial=true`、明确的来源状态
（`error` 或 `generation_drift`），并且不会为该来源伪造记录。消费者不能把
失败来源中缺失的记录解释为“已禁用”或“未注册”。

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
