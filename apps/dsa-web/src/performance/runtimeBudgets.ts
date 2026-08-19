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

/** Virtualize DataTable body rows when at least this many rows are present. */
export const DATATABLE_VIRTUALIZE_THRESHOLD = 24;

/**
 * Estimated default-density DataTable row height (px).
 * py-3 (24px) + text-sm line (~20px) + 1px divider, rounded up to 48.
 */
export const DATATABLE_DEFAULT_ROW_HEIGHT_PX = 48;

/**
 * Estimated compact-density DataTable row height (px).
 * py-2 (16px) + text-xs line (~16px) + 1px divider, rounded up to 36.
 */
export const DATATABLE_COMPACT_ROW_HEIGHT_PX = 36;

/** Extra DataTable rows rendered above/below the visible window. */
export const DATATABLE_OVERSCAN = 6;

/** Max height of the DataTable scroll viewport once virtualization is active (px). */
export const DATATABLE_VIRTUAL_VIEWPORT_PX = 480;

/**
 * Max mounted DataTable body rows when measuring the 150-row contract case
 * (viewport 480px → ~10 visible + 2*overscan + headroom).
 */
export const DATATABLE_MAX_MOUNTED_ROWS_BUDGET = 40;

/** Item count used by the DataTable virtualization measurement entry. */
export const DATATABLE_MEASUREMENT_ITEM_COUNT = 150;

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

/** Signals feed page size used by the pagination measurement. */
export const SIGNALS_LIST_PAGE_SIZE = 20;

/** Item count used by the signals pagination measurement entry. */
export const SIGNALS_LIST_MEASUREMENT_ITEM_COUNT = 150;

/** Candidate count used by the screening mounted-row measurement. */
export const SCREENING_RESULTS_MEASUREMENT_ITEM_COUNT = 150;

/** Max mounted screening body rows once pagination or windowing lands. */
export const SCREENING_RESULTS_MAX_MOUNTED_ROWS_BUDGET = 40;

/** Completed chat bubbles used by the markdown isolation measurement. */
export const CHAT_MARKDOWN_MEASUREMENT_BUBBLE_COUNT = 8;

/** Prior-bubble remounts allowed while live progress updates. */
export const CHAT_MARKDOWN_REMOUNT_BUDGET = 0;

/** Default Home dashboard widget slots that must stay independent. */
export const HOME_WIDGET_SLOT_BUDGET = 4;

/** Shell chrome landmarks (sidebar + main + mobile header). */
export const FIRST_CHROME_LANDMARK_BUDGET = 3;
