# 自选股 AI 评分

自选股评分采用 Route A：只聚合已有分析历史与决策信号，不调用新的 LLM。没有有效分析情绪分的标的返回 `unanalyzed` 和 `score=null`，不会伪造 0 分。

## 公式与来源

当前公式版本为 `watchlist_score_v1`。有效分析情绪分单独存在时，评分等于 0–100 的情绪分；同一分析报告生成的有效决策信号存在时，使用 `0.75 × 情绪分 + 0.25 × 信号分` 并四舍五入。信号动作提示为：`strong_buy=90`、`buy=75`、`hold=50`、`watch=45`、`sell=25`、`strong_sell=10`。置信度存在时，信号分按置信度向中性值 50 收缩。

分析情绪分必须是 0–100 的有限数；信号置信度必须是 0–1 的有限数。非法数值不会参与运算，并通过 `degraded_reasons` 与因子 `reason` 返回原因。

## 信号生命周期与一致性

服务复用 `DecisionSignalRepository` 的到期生命周期，并在读取时再次排除 `expires_at <= now` 的信号。v1 只接受 `source_type=analysis` 且 `source_report_id` 等于最新分析记录 id 的活动信号。旧报告、手工信号、未知动作、非活动或已到期信号不会影响分数。每个因子返回来源 id、报告 id、profile、独立的 `as_of`/`expires_at` 和公式版本。

## 查询与请求边界

`POST /api/v1/watchlist/scores` 最多接受 200 个合法、非重复的市场身份。超限、空白、非法格式、重复别名或未知排序值返回 4xx，不会静默截断。分析和信号分别使用一个数据库窗口查询，按市场规范身份只取稳定的 `(created_at DESC, id DESC)` 第一条；`source_rows` 因此每类最多等于请求身份数。

市场身份复用 `resolve_daily_stock_identity()`。它覆盖 A 股交易所前后缀、港股 `00700`/`HK00700`/`00700.HK`、美股裸代码与 `.US`，以及日、韩、台后缀，并过滤可能跨市场碰撞的数字别名。

## 时间与新鲜度

`AnalysisHistory.created_at` 是历史服务器本地 naive 时间，在分析来源边界按该时区转换为 UTC；`DecisionSignalRecord` 的 naive 时间按 UTC 解释。API 只返回带时区的 RFC3339 时间。未来时钟偏差将年龄收敛为 0；`freshness` 使用固定枚举，具体天数由 `age_days` 表达。

## Web 与集成边界

`WatchlistScoreColumn` 通过因子 key 和 params 在 Web 层本地化，不渲染后端英文标签。默认排序始终为 `manual`；`score_desc`/`score_asc` 只是非破坏性视图，不写回或覆盖 T23 的手工/拖拽顺序。与 #963 的接线契约是把对应 `WatchlistScoreItem` 作为 `item` prop 传给独立组件；本 PR 不修改 `HomeStockWorkspace.tsx`。

## 失败、风险与回滚

聚合失败返回稳定的内部错误，不向客户端暴露异常细节。评分是派生辅助信息，不是投资建议，且可能滞后。回滚只需撤销端点、组件和生成类型；本功能没有迁移或派生持久化数据。若后续 consumer 已接线，应同时撤销其 import 和请求调用。

英文版见 [watchlist-ai-score_EN.md](watchlist-ai-score_EN.md)。
