# 07 Portfolio

Path: **Portfolio**.

## Viewing

1. Select an account or view all.
2. Switch cost method (FIFO / average, as offered).
3. Review KPIs such as market value, P/L, and concentration.
4. Read the risk summary (concentration, drawdown, stop proximity, and related items).
5. Holdings rows may load the latest AI signal asynchronously; an empty placeholder is normal when none exists.

## Bookkeeping

- Create or archive accounts.
- Record trades, cash ledger entries, and corporate actions.
- Filter the event list and correct individual rows.
- Oversell attempts are blocked.

## CSV import

1. Choose a broker template or generic format.
2. Run a dry-run preview first.
3. Commit only after the preview looks correct.
4. Retries should stay idempotent when the client sends a stable operation id.

## Analyze from holdings

Start analysis from a holdings row, track the task, then open the report.  
If the same symbol appears in multiple accounts, pick the account when prompted.

Previous: [06 Signal center](06-signals_EN.md) · Next: [08 Reading reports](08-reading-reports_EN.md)
