// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Decision Signals page URL schema example (UI-03A).
 *
 * Mirrors the query keys already used by DecisionSignalsPage /
 * decisionSignalsPageModel (`getListSearchValues`, `getTimelineSearchValues`,
 * `getStockSearchValues`, `signal`, `view`) so a later migration wave can
 * swap ad-hoc writers for `readParams` / `writeParams` without renaming keys.
 *
 * This file is a **schema-only** foundation. Do not import it from the page yet
 * (page wiring is a follow-up task and must not collide with concurrent work).
 *
 * History mode policy for this page:
 * - List / timeline filters and pagination → replace
 * - Stock context, feed view, selected signal → push (Back restores prior selection)
 */
import {
  defineUrlStateSchema,
  enumParam,
  numberParam,
  optionalStringParam,
  stringParam,
  type InferUrlState,
} from './urlState';

const TIMELINE_RANGES = ['30d', '90d', '180d'] as const;
const TIMELINE_STATUSES = ['all', 'active'] as const;

/**
 * Example schema for Decision Signals feed/list/timeline URL ownership.
 * Signal Center chrome (`scope`/`tab`/`history`/…) stays in
 * `routing/signalCenterRouteState` until a dedicated migration.
 */
export const decisionSignalsUrlSchema = defineUrlStateSchema({
  // --- list filters (replace) ---
  sourceReportId: numberParam({
    name: 'sourceReportId',
    default: null,
    history: 'replace',
    min: 1,
  }),
  market: stringParam({
    name: 'market',
    default: '',
    history: 'replace',
  }),
  listStock: stringParam({
    name: 'listStock',
    default: '',
    history: 'replace',
  }),
  action: stringParam({
    name: 'action',
    default: '',
    history: 'replace',
  }),
  phase: stringParam({
    name: 'phase',
    default: '',
    history: 'replace',
  }),
  source: stringParam({
    name: 'source',
    default: '',
    history: 'replace',
  }),
  /**
   * Default list status is `active` and is omitted from the URL.
   * Explicit `all` (or other statuses) are written as-is.
   */
  status: stringParam({
    name: 'status',
    default: 'active',
    history: 'replace',
    omitEmpty: false,
  }),
  page: numberParam({
    name: 'page',
    default: 1,
    history: 'replace',
    min: 1,
  }),

  // --- timeline filters (replace) ---
  timelineMarket: stringParam({
    name: 'timelineMarket',
    default: '',
    history: 'replace',
  }),
  timelineRange: enumParam({
    name: 'timelineRange',
    values: TIMELINE_RANGES,
    default: '90d',
    history: 'replace',
  }),
  timelineStatus: enumParam({
    name: 'timelineStatus',
    values: TIMELINE_STATUSES,
    default: 'all',
    history: 'replace',
  }),
  timelineProfile: stringParam({
    name: 'timelineProfile',
    default: '',
    history: 'replace',
  }),

  // --- selection / context (push) ---
  stock: optionalStringParam({
    name: 'stock',
    history: 'push',
  }),
  /**
   * Feed view is omitted when it matches the page's contextual default
   * (signals without stock, latest with stock). The schema stores the raw
   * query value; callers apply stock-aware defaulting at the page layer.
   */
  view: optionalStringParam({
    name: 'view',
    history: 'push',
  }),
  signal: numberParam({
    name: 'signal',
    default: null,
    history: 'push',
    min: 1,
  }),
});

export type DecisionSignalsUrlState = InferUrlState<typeof decisionSignalsUrlSchema>;
