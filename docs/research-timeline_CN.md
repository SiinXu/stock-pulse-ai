# 研究时间线（按标的）

## 目的

个股详情页（`/stocks/:stockCode`）展示 **研究时间线** 卡片，聚合该标的的研究活动：

| 类型 | 来源 | 跳转 |
| --- | --- | --- |
| `analysis_run` | `analysis_history` | 分析工作台历史（`recordId`） |
| `chat` | 带 `context_json.stock_code` 的用户轮次 | `/chat?session=…`（turn 身份契约见 #923） |
| `signal` | `decision_signals` | 信号中心（带标的上下文） |
| `hypothesis` | 可选的 #1130 假设工作台 | 工作台未上线前为 `unavailable` |

## API

```http
GET /api/v1/stocks/{stock_code}/research-timeline?cursor=&limit=20&kinds=
```

- **游标分页**：每页每个数据源最多回扫 `limit` 行，按时间倒序合并；不得一次全量拉取。
- **空态诚实**：
  - `empty`：源已实现但无该标的数据
  - `unavailable`：源未上线（当前为假设工作台）
  - UI 区分上述状态，不伪造“成功的空列表”。

## 分析对比

选择两条 `analysis_run` 节点可对比方向与置信度，范围刻意限制为摘要对比，不替代完整报告差异。

其中信号、方向和置信度属于高风险金融文案。八个非源语言译文均标记为
`PENDING_NATIVE_REVIEW`，不声称已经过母语金融审校。

## 相关

- Issue #1137 / Epic #1127
- 假设工作台 #1130
- Chat turn 身份 #923
