// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Portfolio page URL contract (UI-03A / #879 A1) — consumes shared urlState helpers.

import {
  defineUrlStateSchema,
  enumParam,
  numberParam,
  optionalStringParam,
  type InferUrlState,
} from '../../utils/urlState';

/** Primary portfolio workspace tabs. Default (positions) is omitted from the URL. */
export const PORTFOLIO_TAB_VALUES = ['positions', 'ledger', 'risk'] as const;
export type PortfolioTab = (typeof PORTFOLIO_TAB_VALUES)[number];

/**
 * Portfolio shareable URL schema.
 *
 * History policy (encoded on each field; callers may override per write):
 * - tab / page → replace (filter-like refinement)
 * - account → replace by default; user-driven account switches pass history:'push'
 *   so browser Back restores the prior account view (existing unit contract)
 * - selected position row → push (Back restores prior selection)
 *
 * Wire key `account` stays compatible with `parseDeepLink` / notifications.
 * Unknown query keys are preserved by writeParams.
 *
 * Analysis task continuity from task 06 is message-local on main today and is
 * not a URL param; if a task id is added later it should join this schema.
 */
export const portfolioUrlSchema = defineUrlStateSchema({
  account: numberParam({
    name: 'account',
    default: null,
    history: 'replace',
    min: 1,
  }),
  tab: enumParam({
    name: 'tab',
    values: PORTFOLIO_TAB_VALUES,
    default: 'positions',
    history: 'replace',
  }),
  /** Position row identity: `${accountId}-${symbol}-${market}`. */
  selected: optionalStringParam({
    name: 'selected',
    history: 'push',
  }),
  /** Ledger event page (1-based). Omitted when 1. */
  page: numberParam({
    name: 'page',
    default: 1,
    history: 'replace',
    min: 1,
  }),
});

export type PortfolioUrlState = InferUrlState<typeof portfolioUrlSchema>;

export function buildPositionRowKey(accountId: number, symbol: string, market: string): string {
  return `${accountId}-${symbol}-${market}`;
}
