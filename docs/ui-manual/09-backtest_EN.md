# 09 Backtest

Backtest answers:

> Over a past window, did historical AI suggestions look optimistic, conservative, or simply too thin to judge?

- This is **post-hoc checking of advice the system already produced**, not a full quant IDE.  
- It does **not** promise complex slippage, portfolio optimization, or live fill replay.  
- With few samples, pretty percentages are stories first.

> Metrics are **not** promises of future return and are **not** your real fills.

## How to open

| Way | Path |
| --- | --- |
| Nav | **Research → Backtest** |
| URL | `/research/backtest` |
| Palette | “backtest” |
| Legacy | `/backtest` usually redirects |

Example query string:

`/research/backtest?code=600519&window=30&phase=all`

| Param | Meaning |
| --- | --- |
| `code` | Limit to one symbol |
| `window` | Lookback days (capped; often ~120—trust UI) |
| `from` / `to` | Date range |
| `phase` | Session phase filter (pre/in/post) |
| `page` | Pagination |

## When to come / when to wait

| Scenario | Suggestion |
| --- | --- |
| Weeks of real use | Run with a window that matches usage |
| Fresh install, almost no reports | Skip; empty is normal |
| One long-held name | Add `code` |
| With Signal Center review | Center = per-signal lifecycle; this page = batch post-hoc stats |

## Steps

1. Open Backtest.  
2. Optionally enter a code, name, pinyin, or alias in the compact stock field and choose a fuzzy suggestion; also set window, date range, and phase as needed. The single range picker selects the start date first and the end date second.
3. **Filter** refreshes only the results and metrics below; **Run backtest** generates or recalculates evaluations.
4. Read **sample count** before accuracy or win rate.  
5. On empty results, read diagnostics (too few samples, cooling, narrow range)—do not spam-click.
2. Optionally enter a code, name, pinyin, or alias in the compact stock field and choose a fuzzy suggestion; also set window/dates and phase as needed.
3. Optionally set **Min age (days)** and **Candidate limit** (universe size cap) before running; force-rerun still requires confirmation.
4. **Filter** refreshes only the results and metrics below; **Run backtest** generates or recalculates evaluations.
5. After a run, read the **applied config** echo (window, min age, limit, engine, force) so parameter changes are never silent.
6. Read **evaluated / insufficient / total** counts on the performance card before accuracy or win rate.
7. On empty results, read diagnostics (too few samples, cooling, narrow range)—do not spam-click.

An invalid evaluation window no longer changes the input row height: the field shows its error state while the reason remains available to screen readers without adding a trailing control. Validation-mode switches and filter loading also keep stable control widths to avoid toolbar shifts; the Filter tooltip reiterates that filtering does not rerun the backtest.

Skipped and insufficient rows stay in the results table. The **Notes** column surfaces backend `resolution_notes` such as legacy analysis-date fallback, prior-session start after a halt/gap, missing daily bars, or insufficient forward-window bars.

## How to read metrics

| Concept | Meaning | Caution |
| --- | --- | --- |
| Direction accuracy | Move aligned with suggestion direction | Choppy markets look random |
| Win rate | Wins among decisive outcomes | **Sample count first** |
| Simulated return | Rule-based reference | No full friction or psychology |
| TP/SL touch | Whether plan prices were hit | Weak when plans are missing |
| Unable to evaluate | Too new, missing data, cooling | Normal bucket |
| Notes | Why a row was degraded or skipped | Prefer notes over guessing |

Very new rows may sit in a **cooling window** before scoring—protection, not laziness.

## vs Signal Center “Review”

| | Signal Center review | This Backtest page |
| --- | --- | --- |
| Entry | `/signals?tab=review` | `/research/backtest` |
| Best for | Decision Signal lifecycle / outcome engine | Batch post-hoc performance of historical advice |

Both are research tools. Settings “Backtest → engine” is advanced.

## Use cases

**A — Weekend 15 minutes**  
`window=30&phase=all` → enough samples? → if accuracy jumps wildly, inspect Signal Center for many `watch` or intraday phases → adjust habits, not models for luck.

**B — Single-name calibration**  
`code=600519&window=60` → flip-flops? → pair with report history.

**C — Fresh install**  
Empty → normal. Accumulate Workbench reports, return in two weeks.

## Related

- [06 Signal center](06-signals_EN.md)  
- [08 Reading reports](08-reading-reports_EN.md)  
- [11 Daily workflows](11-daily-workflows_EN.md)  

Previous: [08 Reading reports](08-reading-reports_EN.md) · Next: [10 Settings](10-settings_EN.md)
