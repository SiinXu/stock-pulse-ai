# 04 Market review

Market review answers:

> **What is the overall market mood for this session?**

It does **not** answer “should I buy this one stock?”. Keep distance between index strength and your individual holdings.

> **Difference from single-stock analysis**  
> - **Analysis workbench**: research one symbol  
> - **Market review**: market-wide picture (indices, breadth, sectors, sentiment)

> Research only — **not investment advice**.

## How to open

| Way | Path |
| --- | --- |
| Nav | **Research → Market review** |
| URL | `/research/market` |
| Palette | search “market” / “review” |
| Auto-run deep link | `/research/market?action=run` (some Home todos use this) |

If you only want history, open the clean URL `/research/market` without `action=run` so you do not trigger a run by accident.

## When to use

| Scenario | Suggestion |
| --- | --- |
| After the close | Run once; note the main theme and two risks |
| Intraday thermometer | Allowed, but treat “incomplete daily bar” as first-class |
| History already exists | Prefer opening history over re-running every day |
| Combine with watchlist | Review themes → Workbench on specific codes |

## What you will see

1. **Market selector** — use checkboxes for one or more markets, or restore the server default.
2. **Trigger review** — submit a market-level task.
3. **Feedback area** — submitting / running / done / failed / timeout.
4. **Review history** — previous market diaries; multi-select delete may be available.
5. **Report pane** — summary and body for the selected history row.
6. Optional **run flow** — stage breakdown for debugging.

In narrower content areas, review history and the report pane stack vertically. The history rail and report use two columns only on wide screens so empty states are not squeezed into an awkward narrow column.

### Recommended after-close steps

1. Open Market review.  
2. Select markets as needed; keep at least one market or use the server default.
3. Trigger review (label as in UI).
4. Wait for completion; on failure read model / network / data-source errors.
5. Open the newest history row.
6. Read in order: indices → breadth → sectors → risks / data quality.
7. Pick at most 1–2 themes and open [03 Analysis workbench](03-analysis-workbench_EN.md) for individual codes.

## Common report blocks

| Block | What you are reading | Easy misread |
| --- | --- | --- |
| Major indices | Market direction | “Index up = go all-in” |
| Breadth | Advancers vs decliners | “Breadth always continues” |
| Sectors / themes | Who led today | “Every name in a hot sector is chaseable” |
| Risk summary | What to watch | “Official order ticket” |
| Data quality | Degradation / session incompleteness | Overconfidence after ignoring it |

## Glossary

| Term | Meaning |
| --- | --- |
| Breadth | How widely advances/declines are shared |
| Sector rotation | Capital rotating across themes |
| Incomplete daily bar | Today’s bar is not final—discount bravado |
| Run flow | Which stage a job is stuck on |
| recordId | Id of one historical review row |

## Use cases

**A — Minimal close process**  
Trigger → note “main theme + two risks” → at most two related watchlist names into Workbench.

**B — Intraday caution**  
Strong narrative mid-session + incomplete bar / quality warnings → thermometer only; reassess after the close.

**C — History only**  
Clean URL → compare yesterday vs today themes → save one model call.

**D — Failure**  
Model error → Settings test connection; data error → data sources; then trigger once.

## Related

- [03 Analysis workbench](03-analysis-workbench_EN.md)  
- [08 Reading reports](08-reading-reports_EN.md)  
- [11 Daily workflows](11-daily-workflows_EN.md)  

Previous: [03 Analysis workbench](03-analysis-workbench_EN.md) · Next: [05 Agent chat](05-agent-chat_EN.md)
