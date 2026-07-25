# 03 Analysis Workbench: where reports are born

If Home is the front door, the Analysis Workbench is the room where work actually happens.

You enter symbols, optionally pick a strategy Skill, click start, and the system fetches market/news context then asks a large model to write a research report. You can watch task progress live, then reopen history later to compare older calls.

> 💡 **vs Market review**  
> - **Workbench**: one stock (or a batch you chose)  
> - **Market review**: whole-market temperature  
> A strong index does not automatically bless your single name.

> ⚠️ Research only — **not investment advice**. Each run usually costs model quota; start small.

---

## How to open it

| Method | Path |
| --- | --- |
| Nav | **Research** → **Analysis Workbench** |
| Palette | “analysis” / “workbench” |
| URL | `/research/analysis` |
| From Home | **Start analysis** |
| From stock page | **Analyze** on `/stocks/{code}` |

Useful query params: `segment=launch|tasks|history`, `recordId`, `stock`.

---

## Three segments (three conveyor belts)

| Segment | You are… | When |
| --- | --- | --- |
| **Launch** | Entering codes, choosing style, submitting | New work |
| **Tasks** | Watching queue/running/fail | Right after submit |
| **History** | Reading, comparing, deleting | After results exist |

Daily habit: **launch → tasks → history**.

---

## Launch: first report, step by step

1. Open Launch.  
2. Type one code (`600519`, `hk00700`, `AAPL`…).  
3. Leave **Skill** empty the first time.  
4. Prefer **Beginner** and/or **brief** if offered.  
5. **Start analysis**—then wait; do not spam the button.  
6. When complete, **View report** or open History.

### Symbol tips

| Market | Example | Common mistake |
| --- | --- | --- |
| A-shares | `600519` | Company name only |
| HK | `hk00700` | Missing `hk` |
| US | `AAPL` | Chaotic casing |

### Batch without tears

Use after setup works. Submit 3–10 names, watch Tasks for partial failures, re-run only the failed ones. Huge batches get expensive and unreadable.

### Smart import

Image/CSV/clipboard → **human review** of detected codes → then submit. Blurry shots, bad encoding, or missing “code” headers are the usual failure causes.

---

## Tasks: what the states mean

| State | Plain meaning | You |
| --- | --- | --- |
| Queued | Waiting its turn | Patience |
| Running | Fetch + model | Optional run-flow |
| Completed | Ready | Open report |
| Failed | Error mid-flight | Read message → Settings |
| Empty | Nothing running | Back to Launch |

**Run flow** breaks a job into stages for debugging. Skip it until something spins forever.

---

## History: where reports live

Select a row → read summary → open full markdown if needed → use **history trend** to see flip-flops on the same symbol → multi-delete only when you are sure (irreversible).

Bookmark with `segment=history&recordId=…`. Reading order: [08](08-reading-reports_EN.md).

---

## Skills

Optional style packs. First run: none. They change emphasis, not destiny.

---

## Cost & mindset

Detailed + huge batch + spam re-runs burns quota and pollutes Signal Center. Prefer: one clear question → one run → careful read → optional chat follow-up.

---

## Use cases

**A — First report ever** — one symbol, beginner/brief, read action + top risks.  
**B — Weekend watchlist of 8** — batch brief → re-run fails → deep-read top 3 holdings → one price rule.  
**C — Failure** — 401/balance → test connection; timeout → backend/network; data → data-source keys.  
**D — From chart page** — Analyze on `/stocks/AAPL` carries the code for you.

---

## Glossary

| Term | Plain meaning |
| --- | --- |
| Workbench | Main single-stock report factory |
| Segment | Launch / tasks / history |
| Skill | Optional analysis style |
| Run flow | Stage diagnostics |
| recordId | History id in the URL |
| brief/detailed | Report density |

---

## Related

- [08 Reading reports](08-reading-reports_EN.md)  
- [05 Agent chat](05-agent-chat_EN.md)  
- [06 Signal Center](06-signals_EN.md)  
- [13 Stock workspace](13-stock-details_EN.md)  

Prev: [02 Home](02-home_EN.md) · Next: [04 Market review](04-market-review_EN.md)
