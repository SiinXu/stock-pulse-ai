# 事件日历（V0）

面向自选股与持仓的未来事件日历（[#153](https://github.com/SiinXu/stock-pulse-ai/issues/153) / T21）。

## 范围

| 包含 | 不包含（V0） |
| --- | --- |
| 事件模型 + 日期确定性（confirmed / scheduled / estimated） | 全市场事件洪流 |
| 仅自选 + 持仓标的 | 改写 `event_alerts.py` |
| 独立 akshare 取数（不扩 provider 能力表） | 美股/港股完整日历 |
| 影响预览复用 `build_impact_context` | LLM 编造事件本身 |
| Web `/events` 日历视图 | 侧边栏导航接线（见 Integration Point） |

## 开关

```bash
EVENT_CALENDAR_ENABLED=false   # 默认关闭，零额外抓取
EVENT_CALENDAR_ENABLED=true    # 启用后才会调用 akshare 日历源
```

未配置或为 `false` 时，API 返回 `enabled=false`、`fetch_attempted=false`、空事件列表。

## 端点

```http
GET /api/v1/event-calendar
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `date_from` | 今天 | 区间起点 |
| `date_to` | 今天 + 90 天 | 区间终点 |
| `symbols` | 自选∪持仓 | 与托管范围求交，不会扩展到全市场 |
| `event_types` | 全部 | `earnings,ex_dividend,unlock,index_rebalance,macro` |
| `include_impact` | true | 挂载 `build_impact_context` 影响预览 |
| `report_language` | zh | `zh` / `en` |

## 确定性

| 值 | 含义 |
| --- | --- |
| `confirmed` | 已公告的固定日（如已确认除权除息日、解禁批次） |
| `scheduled` | 预约日（如财报预约披露），**可能变动** |
| `estimated` | 预估/推断，最低置信度 |

展示层必须展示确定性标签与 `fetched_at`，避免把预约日当成确定日。

## 影响预览

- 复用 `src/services/event_alerts.py` 的 `build_impact_context` / `why_it_matters`（只读调用，不修改该文件）。
- 不调用 LLM 编造事件；无法评估时 `why_it_matters` 留空。

## 市场覆盖度

| 市场 | 财报 | 除权除息 | 解禁 | 指数调整 | 宏观 |
| --- | --- | --- | --- | --- | --- |
| A 股 | akshare `stock_yysj_em`（预约/实际） | akshare `stock_fhps_em` | akshare 解禁队列 | 未覆盖 (V0) | 未覆盖 (V0) |
| 港股 | 未覆盖 (V0) | 未覆盖 (V0) | 未覆盖 (V0) | 未覆盖 (V0) | 未覆盖 (V0) |
| 美股 | 未覆盖 (V0) | 未覆盖 (V0) | 未覆盖 (V0) | 未覆盖 (V0) | 未覆盖 (V0) |

**不要假设美股/港股日历与 A 股同样完整。**

## Web

- 路由：`/events`（`APP_ROUTE_PATHS.eventCalendar`）
- 组件：`apps/dsa-web/src/components/event-calendar/`（与 `alerts` / `notifications` 分离）

## Integration Point

侧边栏 `SidebarNav.tsx` 本批次冻结。合并后可追加一行导航：

```tsx
{ to: APP_ROUTE_PATHS.eventCalendar, labelKey: 'layout.nav.eventCalendar' }
```

当前可通过直接访问 `/events` 使用。

## 回滚

设置 `EVENT_CALENDAR_ENABLED=false` 或 revert 本变更。
