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

任务队列默认探测是**观测性**的：优先读取已安装 `ApplicationServices` 根上构造时注入的队列（不触达会调用 `get_task_queue()` 的惰性 `task_queue` 属性，也不安装默认根）；否则只读取已经完全初始化的 `AnalysisTaskQueue` 单例。不得走会构造单例、读配置、`sync_max_workers` 或替换/关闭 executor 的 `get_task_queue()`。没有 owner 时检查为 `failed` 且 `reason_code=task_queue_missing`（该检查为 required，整体报告亦为 `failed`）。已有 live / shutdown 状态就地观测，探测不得构造、同步配置、关闭或替换队列状态。`queue=` / `queue_factory=` 注入缝保持不变。

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
