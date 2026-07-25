# 07 Portfolio (Holdings)

Portfolio answers a plain question: **what do you hold, at what cost, and is risk concentrated?**

It cooperates with AI signals; it does not replace them:

- Portfolio stores **your facts** (trades, cash, corporate actions).  
- AI signals are **research suggestions** that may appear beside rows.  
- The product **does not** auto-trade from signals.

> **Why “Portfolio” and “Holdings”?**  
> Sidebar nav is often **Portfolio**; the page title is often **Holdings**. Same module—search either word.

> P&L numbers and AI suggestions are research aids only — **not investment advice**. Keep paper trading (if offered) separate from live books.

## How to open

| Way | Path |
| --- | --- |
| Sidebar | **Portfolio** |
| URL | `/portfolio` |
| Palette | “portfolio” / “holdings” |

## Is this page for you?

| Situation | Suggestion |
| --- | --- |
| Only trying AI reports | You can skip bookkeeping; analysis still works |
| Want “advice vs real size” | Create one account; enter a few trades |
| Broker CSV available | Use import; always preview first |
| Practice without live risk | Use paper/sim account if the UI offers it |

## Page map

```mermaid
flowchart TB
  A[Select account: all or one] --> B[Top KPI and risk]
  A --> C[Holdings table]
  A --> D[Event ledger: trades/cash/corporate]
  A --> E[CSV import]
  C --> F[One-click analysis]
  C --> G[AI suggestion or Signal jump]
```

### Account switcher

- **All accounts**: overview; many write actions may require a specific account.  
- **One account**: bookkeeping and import—confirm the account before every write.

### Cost method

UI may offer **FIFO** and **average cost** (labels as shipped). Changing cost method changes **display** of cost and P&L; it does not erase historical trades. Pick one method and stick to it for self-comparison.

### KPI and risk strip

You may see equity, market value, cash, FX notes, concentration, drawdown, stop proximity, and AI risk summaries. Treat “best-effort quotes / FX caveats” as **directional**, not audited accounting.

### Holdings table

Typical columns: code, qty, cost, last, value, floating P&L, analyze action, optional AI suggestion.

- AI cells may load asynchronously; empty when no active signal is normal.  
- **Analyze** opens a Workbench job—it does not render a full report inside Portfolio.

## First bookkeeping (five steps)

1. **Create account** (name required; broker/currency optional).  
2. **Select that account** (not “All”).  
3. **Enter a buy** (code, date, price, qty; fees if known).  
4. Confirm table qty/cost.  
5. Try an oversized sell—if blocked, protections work.

Then add sells, deposits/withdrawals, dividends as needed.

## Event types

| Type | What you record | Typical fields |
| --- | --- | --- |
| **Trade** | Stock fill | code, buy/sell, price, qty, fees, date |
| **Cash** | Cash in/out | direction, amount, currency, date |
| **Corporate** | Dividend, split | effective date, type, amount or ratio |

Ledger filters by date/code/direction are common. Deletes usually confirm; some deletes are blocked for consistency.

## CSV import

1. Pick broker format or generic template.  
2. **Preview / dry-run** first.  
3. Commit only when preview looks right.  
4. Re-submit should prefer idempotency—avoid double books when the UI says duplicates were skipped.

## One-click analysis from holdings

Row action → track in Workbench → read report with [08 Reading reports](08-reading-reports_EN.md). If the same symbol exists in multiple accounts, pick the account when prompted.

## Use cases

**A — Paper trail for one name**  
One account → one buy of `600519` → analyze from the row → compare suggestion vs size.

**B — Broker CSV**  
Preview → fix mapping errors → import → spot-check qty.

**C — Concentration check**  
All accounts view → read concentration / risk strip → open Signal Center with holdings scope.

## Glossary

| Term | Meaning |
| --- | --- |
| Account | A bookkeeping bucket (live or paper) |
| Cost method | How cost basis is calculated for display |
| Floating P&L | Mark-to-market vs cost under the chosen method |
| Corporate action | Dividend, split, and similar events |
| Dry-run import | Preview without writing |

## Related

- [06 Signal center](06-signals_EN.md)  
- [03 Analysis workbench](03-analysis-workbench_EN.md)  
- [08 Reading reports](08-reading-reports_EN.md)  

Previous: [06 Signal center](06-signals_EN.md) · Next: [08 Reading reports](08-reading-reports_EN.md)
