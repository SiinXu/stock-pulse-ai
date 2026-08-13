# 能力写入注册表与任务感知路由

本文档描述 Issue #221 / #204 的写入侧能力控制面，与只读清单
[`docs/capability-inventory_CN.md`](capability-inventory_CN.md) 互补。

## 边界

| 接口 | 职责 |
| --- | --- |
| `GET /api/v1/capabilities` | 仅投影运行时 owner；不注册、不解析、不写入 |
| `GET/POST /api/v1/capabilities/registry` | 写入侧列表 / 登记 |
| `PUT /api/v1/capabilities/registry/{id}` | 更新未下线条目 |
| `POST /api/v1/capabilities/registry/{id}/retire` | 下线（软删除） |
| `POST /api/v1/capabilities/registry/resolve` | 依赖与版本兼容性解析 |
| `POST /api/v1/capabilities/route` | 可解释的任务感知模型选择 |

注册失败**不会**进入读取侧清单，也**不会**留下“看似成功”的半截快照。

## 安全审计

登记 / 更新 / 下线复用既有特权操作审计链（`capability.write`）。审计不可用时
在持久化前 fail-closed。未授权写入在开启认证时返回 `401`，并留下 `denied`
完成事件。

## 任务路由

`TASK_ROUTING_ENABLED` 默认关闭。开启后按标签与策略从写入侧 `llm` 能力中选择；
`TASK_ROUTING_PIN_*` 始终优先。决策结构为 `task-route-decision/v1`，可写入
运行诊断的 `task_route_decision` 事件以便追溯。

## 延期项

可选 multi-model ensemble 未在本切片交付，仍记在 #204 剩余范围。
