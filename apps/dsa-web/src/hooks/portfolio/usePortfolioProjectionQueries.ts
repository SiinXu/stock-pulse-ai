// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// TanStack Query keys and fetchers for the Portfolio projection session.

import { CancelledError } from '@tanstack/react-query';
import { portfolioApi } from '../../api/portfolio';
import { getParsedApiError } from '../../api/error';
import type { UiLanguage } from '../../i18n/uiText';
import type {
  PortfolioCashDirection,
  PortfolioCashLedgerListItem,
  PortfolioCorporateActionListItem,
  PortfolioCorporateActionType,
  PortfolioCostMethod,
  PortfolioRiskResponse,
  PortfolioSide,
  PortfolioSnapshotResponse,
  PortfolioTradeListItem,
} from '../../types/portfolio';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const PORTFOLIO_PROJECTION_CANCEL = { silent: true, revert: false } as const;

export const PORTFOLIO_PROJECTION_SNAPSHOT_QUERY_KEY_ROOT = [
  'portfolio',
  'projection',
  'snapshot-risk',
] as const;

export const PORTFOLIO_PROJECTION_EVENTS_QUERY_KEY_ROOT = [
  'portfolio',
  'projection',
  'events',
] as const;

/** Previous projection effects never polled, never focus-refetched, and never retried. */
export const PORTFOLIO_PROJECTION_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
} as const;

export const PORTFOLIO_PROJECTION_DEFAULT_PAGE_SIZE = 20;

export type PortfolioEventType = 'trade' | 'cash' | 'corporate';

export type PortfolioEventFilters = {
  dateFrom: string;
  dateTo: string;
  symbol: string;
  side: '' | PortfolioSide;
  direction: '' | PortfolioCashDirection;
  actionType: '' | PortfolioCorporateActionType;
};

export type PortfolioSnapshotRiskQueryData = {
  snapshot: PortfolioSnapshotResponse;
  risk: PortfolioRiskResponse | null;
  riskWarning: string | null;
};

export type PortfolioEventsQueryData =
  | { eventType: 'trade'; items: PortfolioTradeListItem[]; total: number }
  | { eventType: 'cash'; items: PortfolioCashLedgerListItem[]; total: number }
  | { eventType: 'corporate'; items: PortfolioCorporateActionListItem[]; total: number };

export function buildPortfolioProjectionSnapshotQueryKey(
  accountId: number | undefined,
  costMethod: PortfolioCostMethod,
  language: UiLanguage,
): readonly unknown[] {
  return [
    ...PORTFOLIO_PROJECTION_SNAPSHOT_QUERY_KEY_ROOT,
    accountId ?? 'all',
    costMethod,
    language,
  ] as const;
}

export function buildPortfolioProjectionEventsQueryKey(
  accountId: number | undefined,
  eventType: PortfolioEventType,
  filters: PortfolioEventFilters,
  page: number,
  refreshKey: number,
): readonly unknown[] {
  return [
    ...PORTFOLIO_PROJECTION_EVENTS_QUERY_KEY_ROOT,
    accountId ?? 'all',
    eventType,
    filters,
    page,
    refreshKey,
  ] as const;
}

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfProjectionCancelled(signal: AbortSignal | undefined, stillActive: boolean): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(PORTFOLIO_PROJECTION_CANCEL);
  }
}

export async function fetchPortfolioSnapshotAndRisk(args: {
  accountId: number | undefined;
  costMethod: PortfolioCostMethod;
  language: UiLanguage;
  riskFallbackMessage: string;
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<PortfolioSnapshotRiskQueryData> {
  const stillActive = args.stillActive ?? (() => true);
  const snapshot = await portfolioApi.getSnapshot({
    accountId: args.accountId,
    costMethod: args.costMethod,
    includeRealtime: false,
  });
  throwIfProjectionCancelled(args.signal, stillActive());

  try {
    const risk = await portfolioApi.getRisk({
      accountId: args.accountId,
      costMethod: args.costMethod,
      includeRealtime: false,
    });
    throwIfProjectionCancelled(args.signal, stillActive());
    return { snapshot, risk, riskWarning: null };
  } catch (riskError) {
    if (riskError instanceof CancelledError) throw riskError;
    throwIfProjectionCancelled(args.signal, stillActive());
    return {
      snapshot,
      risk: null,
      riskWarning: getParsedApiError(riskError, args.language).message || args.riskFallbackMessage,
    };
  }
}

export async function fetchPortfolioEvents(args: {
  accountId: number | undefined;
  eventType: PortfolioEventType;
  filters: PortfolioEventFilters;
  page: number;
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<PortfolioEventsQueryData> {
  const stillActive = args.stillActive ?? (() => true);
  const dateFrom = args.filters.dateFrom || undefined;
  const dateTo = args.filters.dateTo || undefined;
  const symbol = args.filters.symbol || undefined;

  if (args.eventType === 'trade') {
    const response = await portfolioApi.listTrades({
      accountId: args.accountId,
      dateFrom,
      dateTo,
      symbol,
      side: args.filters.side || undefined,
      page: args.page,
      pageSize: PORTFOLIO_PROJECTION_DEFAULT_PAGE_SIZE,
    });
    throwIfProjectionCancelled(args.signal, stillActive());
    return {
      eventType: 'trade',
      items: response.items || [],
      total: response.total || 0,
    };
  }

  if (args.eventType === 'cash') {
    const response = await portfolioApi.listCashLedger({
      accountId: args.accountId,
      dateFrom,
      dateTo,
      direction: args.filters.direction || undefined,
      page: args.page,
      pageSize: PORTFOLIO_PROJECTION_DEFAULT_PAGE_SIZE,
    });
    throwIfProjectionCancelled(args.signal, stillActive());
    return {
      eventType: 'cash',
      items: response.items || [],
      total: response.total || 0,
    };
  }

  const response = await portfolioApi.listCorporateActions({
    accountId: args.accountId,
    dateFrom,
    dateTo,
    symbol,
    actionType: args.filters.actionType || undefined,
    page: args.page,
    pageSize: PORTFOLIO_PROJECTION_DEFAULT_PAGE_SIZE,
  });
  throwIfProjectionCancelled(args.signal, stillActive());
  return {
    eventType: 'corporate',
    items: response.items || [],
    total: response.total || 0,
  };
}
