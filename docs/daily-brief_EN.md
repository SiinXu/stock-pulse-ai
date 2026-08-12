# Daily Brief (personal morning + historical accuracy)

> 中文：[daily-brief.md](daily-brief.md)

Personal morning push for Issues #149 and #466, with observed earnings-event context from #1131.

- Default off (`DAILY_BRIEF_ENABLED=false`); at most once per local day via runtime scheduler.
- Content: portfolio membership (without comparing unnormalised cross-currency values), overnight Today's Focus, recent earnings EventBrief context, yesterday analyses, watchlist, and honesty-first accuracy.
- `DAILY_BRIEF_QUIET_WHEN_EMPTY` skips notify when no material overnight/event/yesterday content.
- Non-finite metrics are withheld as unavailable, and output is capped at 24,000 characters.
- Notification uses the shared `report` route and structured per-channel dispatch; one channel failure does not block analysis. History `report_type=daily_brief` is a durable inbox source (#181).

See also [event-research-brief_EN.md](event-research-brief_EN.md).
