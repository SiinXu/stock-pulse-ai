# 07 Portfolio (Holdings): clear books before clever signals

This module answers a plain question: **what do you hold, roughly at what cost, and is risk bunched in too few names?**

- Portfolio rows are **your facts** (trades, cash, dividends).  
- AI signals are **research hints** that may appear beside rows.  
- The app **does not** auto-trade from those hints.

> 💡 Sidebar often says **Portfolio**; the page title may say **Holdings / portfolio management**. Same place.  
> ⚠️ Research/record-keeping only — **not investment advice**. Keep paper accounts (if any) separate from live cash stories.

## Open it

Sidebar **Portfolio**, URL `/portfolio`, palette “portfolio/holdings”.

## When you need it

Trying AI reports only? Skip for now. Want advice vs real size? Create one account and a few trades. Have a broker CSV? Import with preview. Want practice? Use paper/sim if the UI offers it.

## Layout in plain words

Pick **all accounts** (overview; writes may be blocked) or **one ledger** (where you bookkeep). Switch **cost method** (FIFO / average—as labeled); it changes presentation, not historical trade rows. Read KPIs and risk as **direction**, especially when limitation tags say quotes or FX are partial. The positions table shows qty/cost/last/P&L, **Analyze** (sends a Workbench job), and an async AI column that may stay empty without active signals.

## From zero in five gentle steps

1. Create an account (name required).  
2. Select that account—not “all”.  
3. Enter one buy.  
4. Check qty/cost.  
5. Try an oversell on purpose; a block means safeguards work.

## Three event types

| Type | What you record |
| --- | --- |
| **trade** | Buys/sells with price, qty, fees |
| **cash** | Deposits/withdrawals |
| **corporate** | Dividends, splits, …

Filters, paging, delete confirms. Wrong account = wrong ledger—double-check.

## CSV import, kindly

Select account → choose file → broker/generic template → **parse/dry-run** → sample-check three symbols → **commit** → reconcile with the broker app. Fix headers/encoding/duplicates in preview, not after regret.

## With AI signals

Empty AI cells are normal without active signals—run Workbench on holdings or open `/signals?scope=holdings`. Degraded badges mean open the full signal/report. Pre-open habit: concentration + drawdown → analyze the one name that worries you.

## Use cases

Three manual trades only; large CSV with dry-run; holdings without AI until analysis runs; multi-account same symbol—pick the right ledger when prompted.

## Related

- [06 Signal Center](06-signals_EN.md)  
- [03 Analysis Workbench](03-analysis-workbench_EN.md)  
- [11 Daily workflows](11-daily-workflows_EN.md)  

Prev: [06 Signal Center](06-signals_EN.md) · Next: [08 Reading reports](08-reading-reports_EN.md)
