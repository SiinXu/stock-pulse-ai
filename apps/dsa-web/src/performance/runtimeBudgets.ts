/**
 * Runtime performance budget constants shared by product code and contract tests.
 * Source of truth for threshold numbers also lives in
 * `scripts/runtime-performance-budget.json` (soft-gate checker + docs).
 * Keep both in sync when tightening budgets.
 */

/** Virtualize HistoryList when at least this many items are loaded. */
export const HISTORY_LIST_VIRTUALIZE_THRESHOLD = 24;

/** Estimated history row height used for window sizing (px). */
export const HISTORY_LIST_ESTIMATED_ROW_HEIGHT_PX = 72;

/** Extra rows rendered above/below the visible window. */
export const HISTORY_LIST_OVERSCAN = 6;

/**
 * Max mounted history rows when measuring the 150-item contract case
 * (viewport 480px → ~7 visible + 2*overscan + small headroom).
 */
export const HISTORY_LIST_MAX_MOUNTED_ROWS_BUDGET = 40;

/** Item count used by the list virtualization measurement entry. */
export const HISTORY_LIST_MEASUREMENT_ITEM_COUNT = 150;

/** Fixed viewport height used by the list measurement harness (px). */
export const HISTORY_LIST_MEASUREMENT_VIEWPORT_PX = 480;

/** Field count used by the Settings isolation measurement entry. */
export const SETTINGS_FIELD_MEASUREMENT_COUNT = 40;

/** Max sibling SettingsField re-renders allowed after a single field edit. */
export const SETTINGS_FIELD_SIBLING_RERENDER_BUDGET = 0;

/** Progress event count used by the SSE batching measurement entry. */
export const SSE_PROGRESS_MEASUREMENT_EVENT_COUNT = 60;

/**
 * Max progressSteps store commits allowed while draining a 60-event burst.
 * Includes stream setup and terminal cleanup; not wall-clock frame timing.
 */
export const SSE_PROGRESS_COMMIT_BUDGET = 4;
