# Daily Brief (personal morning + historical accuracy)

> 中文：[daily-brief.md](daily-brief.md)

Personal morning push for Issues #149 and #466, with earnings event foresight from #1131.

- Default off (`DAILY_BRIEF_ENABLED=false`); at most once per local day via runtime scheduler.
- Content: portfolio holdings, overnight Today's Focus, earnings EventBrief foresight, yesterday analyses, watchlist, honesty-first accuracy.
- `DAILY_BRIEF_QUIET_WHEN_EMPTY` skips notify when no material overnight/event/yesterday content.
- Failures never block sibling notification work. History `report_type=daily_brief` is a durable inbox source (#181).

See also [event-research-brief_EN.md](event-research-brief_EN.md).
