# 03 Analysis workbench

Path: **Research → Analysis** (or search “analysis” in the command palette).

The page usually has three segments:

| Segment | Purpose |
| --- | --- |
| Launch / batch | Enter symbols, pick strategies, submit jobs |
| Running tasks | Progress and failure reasons |
| History / compare | Open reports, trends, delete |

URLs may include `segment`, `recordId`, and related parameters to restore state.

## Start an analysis

1. Enter a code such as `600519`, `hk00700`, or `AAPL`.
2. Optionally pick from the watchlist.
3. Optionally choose a strategy skill; otherwise the system default applies.
4. Optionally switch beginner / pro mode or report detail level.
5. Submit the job.
6. Watch **Running tasks** until completion.
7. Open the history report or follow the completion link.

### Batch and import

- Batch jobs appear as separate task rows.
- **Smart import** accepts screenshots, CSV/Excel, or clipboard text; confirm the list before submit.

### Code formats

| Market | Examples |
| --- | --- |
| A-shares | `600519`, `300750` |
| Hong Kong | `hk00700` |
| US | `AAPL`, `BRK.B` |
| Japan / Korea | `7203.T`, `005930.KS` |

## Task progress

- Typical states: queued, running, completed, failed.
- In-progress text may show stages (quotes, news, generation).
- “Auto phase” means calendar-based inference; the final phase label is on the report page.
- On failure, read the error before retrying.

## History and compare

1. Open a history row for the full report / Markdown.
2. Use history trend for the same symbol across runs.
3. Multi-delete requires confirmation.
4. Market-review history is separate from stock history.

## Beginner vs pro mode

| Mode | Experience |
| --- | --- |
| Beginner | Shorter conclusions, more conservative risk framing |
| Pro | Full fields, trends, more detail |

Mode preference is usually stored locally and may survive logout.

## Continue in chat

If the report offers **Ask / Chat**, the session should keep the current symbol context. See [05 Agent chat](05-agent-chat_EN.md).

Previous: [02 Home](02-home_EN.md) · Next: [04 Market review](04-market-review_EN.md)
