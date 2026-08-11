# 05 Agent chat (Ask stock)

Agent chat is a **multi-turn research assistant**. Best use is not “guarantee profits from zero”, but:

> I already have a report. I do not understand this section / I want to check invalidation / I want a careful comparison—let’s talk it through.

Sidebar label is often **Agent**; page title is often **Ask stock** (or similar). Same entry—do not treat them as two products.

> **Division of labor with Workbench**  
> - **Analysis workbench**: structured reports, history, extractable signals  
> - **Agent chat**: follow-up Q&A on a report or a symbol  
> Stable order: **report first, then chat**.

> Research only — **not investment advice**. Chatty tone is not an order ticket.

## How to open

| Way | Notes |
| --- | --- |
| Sidebar **Agent** | Primary entry |
| URL `/chat` | Bookmarkable |
| **Continue in chat** on a report | Brings stock context—recommended |
| Command palette | search “agent”, “chat”, “ask” |

## First conversation

1. Confirm **which symbol** you are discussing. Report entry usually sets this; otherwise write the code in the question (e.g. “discuss 600519 only”).  
2. First question = one thing (invalidation, support/resistance basis), not “full analysis and max position”.  
3. Wait for the reply to finish before the next turn.  
4. When switching symbols: **new chat**, or clearly write “switch to 300750; do not mix the previous name”.  
5. Useful conclusions can be exported or turned into a manual signal / rule in Signal Center.

### Safer rewrites of example prompts

UI may show casual samples. Prefer research-oriented phrasing:

- “List current invalidation conditions for 600519 as bullets.”  
- “Explain support and resistance in plain language and say whether each level is technical or event-driven.”  
- “Do not give position size; only discuss observation conditions.”

## Page controls (typical)

| Control | Role | Tip |
| --- | --- | --- |
| History list | Past sessions; outside the main content frame on wide screens | Delete noise regularly |
| New chat | Clean context | Use when changing topic |
| Input + send | Ask | Avoid double-submit while generating |
| Stop | Interrupt generation | Partial text may remain |
| Delete message / session | Cleanup | Usually irreversible |
| Export | Keep research notes | Good for weekend review |
| Notify | Push to a channel | Needs a working channel in Settings |
| Watchlist add/remove | Sync watchlist | Same list as Settings |
| Strategy expand | Choose a Skill | Beginners can skip |
| Deep-research stock field | Scope a research question to a symbol | Supports code/name suggestions; suffix and manual-entry guidance is in the adjacent help tooltip |
| Run in background | Leave the research panel while the backend continues | The question enters the current conversation immediately; the report or stable failure record follows in the same conversation |
| Generate analysis | Heavier path | Costs more; use deliberately |
| Thinking / reasoning pane | Stage status and tool calls | Expand a completed tool row to inspect redacted arguments, cache state, result length, and a bounded result preview |
| Context compression | Save tokens on long chats | Compact control row; check unsaved state after edits |

Deep Research assigns a bounded share of the total deadline to each sub-question, reserves time for final synthesis, and ends the API wait explicitly when the overall deadline is reached. The research question, completed report, and stable failure record are stored in the current conversation and therefore appear in conversation history. Choosing **Run in background** or leaving the page does not interrupt research in the current server process; reopen the conversation to read the result. A backend process restart can still interrupt an active run and is not resumable. If one search stage times out, already collected bounded evidence is retained for the report. Sequential plain-text planning output is still parsed into separate sub-questions, and planning or synthesis responses that contain reasoning but no final text are retried with a larger output budget. Reports produce the executive summary and conclusion recommendations before expanding long details. If no usable conclusion is produced, the run fails closed instead of showing a blank successful result; the top Toast reports the failure and the existing form can retry it.

Successful Agent replies persist the public details of up to 32 completed tool calls, so they remain expandable after a refresh or reopening the conversation. The UI does not expose hidden model reasoning, API keys, provider traces, or complete unbounded responses; arguments and result previews are redacted and length-limited. Older messages created before these fields were persisted still show the tool name, status, and duration, but their missing details cannot be backfilled.

## Strategy / Skill — should you pick one?

Optional. Skills bias evidence emphasis (trend, quality, event, … as listed).

- First follow-up: **leave unset** to reduce variables.  
- Choose only when you intentionally want a style.  
- Never a “guaranteed win” switch.

## When send fails

1. Settings → model connection test.  
2. Confirm that the selected Agent generation method is available. Local CLI requests tools through the controlled bridge; if its executable is missing, install and log in to that CLI or select an available API model.
3. Network / rate limits: wait and retry once; read the on-page error.

## Use cases

**A — After first report**  
Open report → Continue in chat → ask only invalidation → optional feedback in Signal Center.

**B — Compare carefully**  
New chat; “Compare risk factors of 600519 vs 000001 without position advice.”

**C — Tools unavailable**  
Error mentions a missing local CLI executable → Settings / Agent generation method → install and log in to that CLI, or select an API path.

## Glossary

| Term | Meaning |
| --- | --- |
| Agent / Ask stock | Same module, different labels |
| Skill / strategy | Optional analysis style pack |
| Context compression | Shorten long history to save tokens |
| Tool use | Agent calling bounded tools when the backend allows |

## Related

- [03 Analysis workbench](03-analysis-workbench_EN.md)  
- [08 Reading reports](08-reading-reports_EN.md)  
- [06 Signal center](06-signals_EN.md)  
- [10 Settings](10-settings_EN.md)  

Previous: [04 Market review](04-market-review_EN.md) · Next: [06 Signal center](06-signals_EN.md)
