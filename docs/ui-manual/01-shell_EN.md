# 01 Shell and global actions

The **shell** is the frame that stays around almost every page: primary navigation, notification bell, search / command entry, language and theme. Once you know the shell, moving between features is much easier.

> 💡 **What this chapter is for**  
> Not server config files — only **where to click**, shortcuts, and how **UI language** differs from **report language**.

## When you use the shell

| Scenario | Shell piece |
| --- | --- |
| First open; where is everything? | Primary nav + command palette |
| Jump back to analysis from anywhere | `Cmd/Ctrl + K` → “analysis” |
| Check new reminders | Notification bell |
| English menus, Chinese reports (or the reverse) | UI language vs report language |
| Screen glare at night | Theme (light / dark) |

## Layout

```mermaid
flowchart TB
  subgraph shell [Shell]
    N[Primary nav]
    B[Notification bell]
    K[Command palette / search]
    L[Language and theme]
  end
  subgraph main [Main content]
    P[Active page: Home / Analysis / Signals / ...]
  end
  N --> P
  K --> P
  B --> S[Deep link into Signal center]
```

| Area | Typical location | Purpose | Plain meaning |
| --- | --- | --- | --- |
| **Primary nav** | Left on wide screens; top or drawer on narrow | Home, Research, Signals, Portfolio, Settings | The “table of contents” |
| **Main content** | Center | Active feature page | The “body” |
| **Notification bell** | Top or upper sidebar | Latest **signals** and **alerts** | “Anything new?” |
| **Search / command** | Sidebar search or shortcut | Jump pages, find tickers, some global actions | “Universal search” |

Desktop and Web share the same **information architecture** (how features are grouped). Desktop-only windows follow the shipped client.

> ⚠️ **Narrow screens**  
> The left nav may collapse into a menu icon. If you cannot find Settings, open that menu or use the command palette.

## Common nav groups

| Nav label (follow live UI) | Rough contents | Manual chapter |
| --- | --- | --- |
| Home | Focus and todos | [02 Home](02-home_EN.md) |
| Research | Analysis workbench, market review | [03](03-analysis-workbench_EN.md), [04](04-market-review_EN.md) |
| Agent chat | Multi-turn Q&A | [05 Agent chat](05-agent-chat_EN.md) |
| Signals | Advice pool, rules, delivery history | [06 Signal center](06-signals_EN.md) |
| Portfolio | Accounts and risk | [07 Portfolio](07-portfolio_EN.md) |
| Settings | Models, watchlist, notifications | [10 Settings](10-settings_EN.md) |

Labels may shift slightly by version; trust the live UI.

## Command palette (worth learning)

| OS | Shortcut |
| --- | --- |
| macOS | `Cmd + K` |
| Windows / Linux | `Ctrl + K` |

| Intent | Example | Result |
| --- | --- | --- |
| Jump to a page | `analysis`, `portfolio`, `signals` | Opens that page |
| Find a stock | `600519`, `AAPL` | Related analysis entry (version-dependent) |
| Global action | e.g. market review | Listed when the build supports it |

### Example: three steps back to analysis

1. You are in Settings editing a model.  
2. Press `Ctrl + K` / `Cmd + K`, type “analysis”.  
3. Open Running tasks or History on the workbench.

> 💡 **Why it is faster**  
> Typing beats hunting nested menus, especially on small screens.

## Notification bell

| Type | Meaning | Typical landing |
| --- | --- | --- |
| **Decision signal** | Structured advice extracted from an analysis | A Signal center row |
| **Alert** | A rule you defined fired (e.g. price cross) | Alert / rules related view |

1. Open the bell.  
2. Click an item to **deep-link** into Signal center.  
3. Unread state for signals and alerts is usually separate; clearing site data may reset it.  
4. Partial channel failure shows a retryable warning — do not treat newly recovered items as already read.

> ⚠️ **Empty bell is often normal**  
> No successful single-stock analysis and no alert rules yet → empty is expected. Run your first report via [03 Analysis workbench](03-analysis-workbench_EN.md).

## UI language vs report language

| Type | Affects | How to change | Cross-linked? |
| --- | --- | --- | --- |
| **UI language** | Nav, buttons, settings chrome | In-app switch (often zh/en), including before login when available | **Does not** change report language |
| **Report language** | Report body and some notification report copy | **Settings** (often `zh` / `en` / `ko`) | **Does not** change menu language |

### Examples

- English **menus**, Chinese **reports**: switch UI language only; keep report language `zh`.  
- English **reports** for a colleague: change report language in Settings; menus can stay Chinese.

> 💡 **Terms**  
> - **UI (user interface) language**: labels on controls.  
> - **Report language**: long-form model output and fixed report chrome.

## Theme

| Item | Note |
| --- | --- |
| Where | Settings or top bar (follow live UI) |
| Storage | Local browser or desktop client |
| Tip | Dark theme is comfort only; it does not change analysis logic |

## Shell-level habits

| Habit | Why |
| --- | --- |
| **Save** settings and wait for success | Unsaved = not applied; Home may still show gaps |
| Prefer the command palette for cross-page jumps | Faster on narrow layouts |
| Keep UI language and report language distinct | Avoid false expectations |
| Empty bell → run analysis first | Before debugging “notifications broken” |

## Desktop client

| Item | Note |
| --- | --- |
| Menu structure | Aligned with Web so one manual covers both |
| Desktop-only features | Tray, floating assistant, etc. follow the shipped client |
| Install and first API key | [Beginner client setup](../beginner-client-setup.md) (Chinese); not part of shell clicks |

## Related

- [02 Home](02-home_EN.md)
- [10 Settings](10-settings_EN.md)
- [06 Signal center](06-signals_EN.md)

Previous: [Manual home](README_EN.md) · Next: [02 Home](02-home_EN.md)
