# EvolutionEvent 存储

**状态**：issue [#1113](https://github.com/SiinXu/stock-pulse-ai/issues/1113) 在史诗 [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107) 下的第一段有界切片

**English**: [evolution-events.md](evolution-events.md)

本文描述仅追加的 `EvolutionEvent` 持久化、仓库层类型化查询，以及已认证的 HTTP 列表。它**不是**特权操作安全审计、不是 episode 存储、不是策展等级写入，也不是预测解析器里名为 `EvolutionEventSink` 的进程日志。

本切片**不关闭** #1113。校准生效路径已在 main 上写 `adapter.calibrate`（Refs #1106）。tool-rank、route-bias、实验开关生产者和 Web UI 仍开放。#1113、#1107、#1091、#1106、#1093 保持开放。

## 目的

为后续生产者提供可检查的自动进化记录：改了什么、为什么改、变更前后快照是什么。

| 字段 | 契约 |
| --- | --- |
| `event_id` | 追加时生成的不可变唯一 id |
| `occurred_at` | 带时区的 UTC 时间戳（库内以 UTC naive datetime 存储） |
| `event_type` | 非空精确类型字符串 |
| `actor` | 白名单：`system` \| `user` \| `operator` |
| `reason_refs` | 仅结构化 `{prediction_ids, run_ids}`。允许空列表：存储层不虚构关联 id。后续自动生产者必须填入已知 id；缺失不等于虚构变更。 |
| `before` / `after` | JSON 安全且有界的快照对象。规范化后 `before` 必须不同于 `after`。相同或均为空的快照会被拒绝，因为本日志审计真实变更而非空操作。 |

## 模块

| 路径 | 职责 |
| --- | --- |
| `src/schemas/evolution_event.py` | 严格的创建/查询契约与载荷边界 |
| `src/repositories/agent_evolution_event_tables.py` | SQLAlchemy 表投影 |
| `src/repositories/agent_evolution_event_repo.py` | 仅追加与含端点的 UTC 时间/类型查询 |
| `src/migrations/versions/v202608250003_agent_evolution_event_schema.py` | 表、索引、禁止 UPDATE/DELETE 的 trigger |
| `src/services/evolution_event_query.py` | HTTP 用的只读 `list_events` 薄封装 |
| `src/api/v1/endpoints/evolution_events.py` | 已认证 `GET /api/v1/agent/evolution-events` |
| `src/api/v1/schemas/evolution_events.py` | HTTP `{items, limit, returned}` 列表响应 |

没有配置开关。仍无 Web、Desktop 或 CLI 查询。HTTP 列表不会追加事件。

## 数据库仅追加边界

`agent_evolution_events` 只由有序 migration runner 创建（紧接 `202608250002_agent_curator_grade_schema` 之后）。SQLite trigger 会中止对历史行的 `UPDATE` 与 `DELETE`。降级只删除该表、其索引与 trigger。episode、预测、策展等级、安全审计事件和解析器进程日志不受影响。

## 查询

`AgentEvolutionEventRepository.list_events`：

- 含端点的 UTC `occurred_from` / `occurred_to`（必须带时区；`from > to` 失败关闭）
- 可选的**精确** `event_type`。只有 `event_type=None` 才省略该过滤。空白或纯空格失败关闭，避免错误过滤条件被静默放宽成全量查询。
- 有界 `limit`（默认 100，最大 200）
- 确定性排序：先 `occurred_at ASC`，再 `id ASC`
- 无匹配行返回空列表，而不是错误

无时区时间戳与非法 limit 会被拒绝。

## HTTP 列表

`GET /api/v1/agent/evolution-events` 是公开只读路径，沿用仓库的时间窗、精确类型和 limit 契约：

- 必填带时区的 `occurred_from` / `occurred_to`（含端点）。无时区或 `from > to` 返回 `400 validation_error`。
- 可选精确 `event_type`。省略参数则不加类型过滤。空白或纯空格返回 `400`，避免错误过滤被静默放宽成全量列表。
- 可选 `limit`（默认 100，最大 200）。`0` 或 `201` 返回 `400`。
- 额外查询键拒绝（`422`）。
- 空窗口返回 `200` 且 `items: []`。响应形状为 `{items, limit, returned}`，没有 total。
- 认证与其他 Agent 读接口一致（`AdminSessionCookie`）。`ADMIN_AUTH_ENABLED=true` 时缺少或无效会话返回 `401`。认证关闭时允许本地读取。该路径不在 `EXEMPT_PATHS` 中，也不使用安全审计“认证关闭则 403”的规则。
- 仅 GET。不调用 `append`。

## 隐私

快照与 `reason_refs` 必须 JSON 安全且有大小上限。Schema 拒绝密钥、完整系统 prompt、原始供应商载荷、Agent Soul 宪章文本以及非有限数字。快照键会把 camelCase、连字符和点号形式（`accessToken`、`system-prompt`、`provider.payload`）规范成 snake_case 后再匹配禁止集合。不要持久化 API key、token、`system_prompt`、`provider_payload` 或同类键。

## 生产者策略

门控置信度校准在因子实际生效时追加一条 `actor=system` 的 `adapter.calibrate` 行（Refs #1106）。身份桩、开关关闭路径和样本不足路径不得虚构行。episode 遗忘/压缩已在同一删除事务里写仅元数据事件。

**写事件失败必须记录日志，且不得改变预测 `status` / `outcome_json` 或适配器返回值。** 生产者捕获 append 失败、记录脱敏警告并继续。不得新增 update/delete API，不得改适配器返回值，也不得从事件路径写预测行。仓库 `append` 本身仍失败关闭。HTTP 列表只读，不发射事件。

tool-rank、route-bias、实验 skill 开关和 Web UI 仍是后续遗留。本 HTTP 切片不替换解析器 `EvolutionEventSink`。

## 非范围

- tool-rank / route-bias / 实验开关变更（#1091 / #1106 / #1093 遗留）
- Web、Desktop 或 CLI 查询界面
- 配置注册表键或 README 首页变更
- 复用 `security_audit_events`
- EvolutionEvent 的 POST / PATCH / DELETE HTTP

## 回滚

回退 HTTP 列表变更集。无 migration。已有 `agent_evolution_events` 行保持不变。
