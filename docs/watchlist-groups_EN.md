# Watchlist Groups

Watchlist groups organize `STOCK_LIST` symbols by theme or strategy on the Web home page. A symbol may belong to multiple groups, but groups do not change the global watchlist consumed by analysis, alerts, CLI commands, or scheduled tasks.

## Data and identity contract

- `STOCK_LIST` is the sole membership authority. Group tables store only placement, ordering, and read-only computed attributes for authoritative symbols.
- Every entry point uses one market-aware identity rule. `00700.HK`, `HK00700`, and `00700` converge to one `HK00700` member.
- Before every group read, one database transaction prunes symbols removed from `STOCK_LIST`, deduplicates aliases, seeds missing symbols, and repairs contiguous ordering. Adding a new symbol commits `STOCK_LIST` first; if the group write then fails, the next read recovers the symbol into Default while preserving the visible error.
- The default group uses the reserved `default` key. Its display text is not stored in a user language; the Web client renders the stable `watchlist.defaultGroupName` localization key.

## Concurrency and bounds

Every response contains a monotonically increasing `revision`. Before any business write, the server acquires the revision write lease with an atomic compare-and-swap. Concurrent mutations using the same revision therefore produce one success and `409 watchlist_group_revision_conflict` for the others instead of leaking a uniqueness race as `500`. The client then reloads server state. Reorder payloads must contain every current group ID or member code exactly once, otherwise the API returns `400`.

Read reconciliation acquires the database write lease and then revalidates the system configuration `config_version` while holding that lease. If `STOCK_LIST` changes after the snapshot was read, the server discards the stale snapshot and retries a bounded number of times. This prevents a stale reconciliation from deleting a placement committed by another request; continuous changes beyond the retry limit return `409 watchlist_group_authority_changed`.

The default bounds are 50 groups, 500 members per group, and 2,000 total memberships. Names are limited to 80 characters. Computed attributes use a versioned, read-only schema: `schema_version=1`, optional finite `ai_score` from 0 to 100, and optional boolean `focus`. Clients cannot persist arbitrary JSON.

## Interaction and accessibility

Desktop drag starts only from a visible handle; the same handle supports Arrow Up and Arrow Down. Mobile DOM is not draggable and exposes explicit move-up, move-down, and Move-to-group actions. Menus support Escape, outside click, focus return, and screen-reader live announcements. The Web client clears a new-group draft or announces reorder/move success only after the server confirms the mutation; failures retain the draft, expose the error, and never announce false success.

## Upgrade, backup, and recovery

Upgrade creates `watchlist_groups`, `watchlist_group_members`, and `watchlist_group_state`. The first read creates Default and imports the existing `STOCK_LIST`; no manual migration is required. Back up the application database and the `.env` or system configuration containing `STOCK_LIST` before upgrading.

If a dual-write interruption is suspected, verify `STOCK_LIST` and read the groups API again. Transactional reconciliation restores membership and ordering invariants. Logs retain diagnostics under `watchlist_group_internal_error`; public 500 responses never expose database paths or driver errors.

## Rollback

Older code ignores the additive tables after a code rollback. Running the migration downgrade deletes all three tables and permanently removes group names, ordering, and computed attributes, so back up the database first. Downgrade never changes `STOCK_LIST`, and the global watchlist remains usable.
