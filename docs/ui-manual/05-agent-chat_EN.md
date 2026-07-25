# 05 Agent chat: after the report, ask what still feels fuzzy

Hi. Chat is a **multi-turn research assistant**. Its best use is not “promise me returns from zero”, but:

> I already have a report—this section confuses me / I want invalidation / I want a careful compare—let’s talk it through.

Sidebar may say **Agent**; the page title often says **Ask stock**. Same door.

> 💡 **vs Workbench** — Workbench builds the structured report; chat follows up. Prefer **report first, then questions**.

> ⚠️ Research only — **not investment advice**.

---

## Open chat

Sidebar **Agent**, URL `/chat`, report **Continue in chat** (best—keeps symbol context), or the command palette.

---

## First conversation, gently

1. Confirm the **symbol** (type the code if unsure).  
2. One focus per turn—start with invalidation, not “full analysis + max leverage”.  
3. Wait for the reply before the next question.  
4. Changing symbols: **new conversation** or explicit “switch to 300750 only”.  
5. Export useful bits, or turn levels into Signal Center rules.

Rewrite empty-state examples into research-friendly prompts (“list invalidation conditions…”, “no position sizes…”).

---

## What else is on the page

Session list, new chat, send/stop, delete, export, notify (needs channels), watchlist add/remove, strategy panel, heavier **generate analysis**, thinking block (reference, not scripture), context compression (save it).

---

## Skills

Optional. First follow-up: skip. They change emphasis, not outcomes.

---

## When send fails

1. Model saved + test connection?  
2. Backend that cannot tool-call (local CLI limits)? Check task routing.  
3. Network/backend up?  
4. Notify failure ≠ chat failure—test channels separately.

---

## Saving quota kindly

Brief report first → chat only on 1–2 unclear points → compression on long threads → new session with a three-line summary if the model “forgets”.

---

## Use cases

Invalidation after a report; avoid symbol mix-ups with explicit codes; compare AAPL vs MSFT without position sizes; holdings: observation conditions only, no sizing orders.

---

## Related

- [03](03-analysis-workbench_EN.md) · [08](08-reading-reports_EN.md) · [06](06-signals_EN.md) · [10](10-settings_EN.md)

Prev: [04 Market review](04-market-review_EN.md) · Next: [06 Signal Center](06-signals_EN.md)
