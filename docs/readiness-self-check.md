# 结构化就绪 / 自检

Issue: [#1071](https://github.com/SiinXu/stock-pulse-ai/issues/1071)

英文版见 [readiness-self-check_EN.md](./readiness-self-check_EN.md)。

## 目的

运维与首启需要一份 **统一、失败显式（fail-closed）** 的就绪投影，覆盖行情数据源、LLM/生成后端、任务队列容量，以及部分 setup 依赖（存储、自选股、通知、Agent）。

## 模块

```text
src/core/readiness.py
```

报告 schema：`readiness_v1`。状态：`ok` | `degraded` | `failed`，附带 `reason_code` / `reason` / `suggestion`。

整体聚合：任一 required 的 `failed` → 整体 `failed`；否则存在 `failed`/`degraded` → `degraded`；否则 `ok`；检查列表为空 → `failed`。

## 整合原则

复用既有观测探针（setup status、data provider runtime status、generation backend cheap status、task queue stats），不另造并行健康体系。首启 / setup 原有 API 契约保持不变。

## API

```http
GET /api/v1/system/readiness
```

只读、不写配置、不跑模型 smoke、不在进程启动时自动调用。探测异常与单检查超时不得报 `ok`。generation-backend 状态载荷字段与测试义务见 [共享运行时 session 契约所有权](runtime-session-contract-owners_CN.md)。

## 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `READINESS_CHECK_TIMEOUT_SECONDS` | `1.0` | 单检查超时（秒），钳制在 `0.1`–`5.0` |

已登记 config registry，并进入共享 `Config.readiness_check_timeout_seconds`。
