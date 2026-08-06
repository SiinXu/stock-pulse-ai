// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Pure helpers for Portfolio position-signal lookup and limitation labels.

import { decisionSignalsApi } from '../../api/decisionSignals';
import { getParsedApiError } from '../../api/error';
import type { DecisionSignalItem, DecisionSignalMarket } from '../../types/decisionSignals';
import type { UiLanguage } from '../../i18n/uiText';
import { PORTFOLIO_LIMITATION_LABELS } from '../../locales/portfolio';
import { normalizeStockCode } from '../../utils/stockCode';
import { parseDecisionSignalDate } from '../../utils/decisionSignalTime';
import { getDecisionSignalPresentation } from '../../utils/decisionSignalPresentation';

export type PortfolioSignalLookup = {
  stockCode: string;
  market?: DecisionSignalMarket;
};

export type PortfolioSignalLookupResult = {
  items: DecisionSignalItem[];
  error: string | null;
};

const DECISION_SIGNAL_MARKETS = new Set<DecisionSignalMarket>(['cn', 'hk', 'us', 'jp', 'kr', 'tw']);

export function getSignalTime(item: DecisionSignalItem): number {
  return parseDecisionSignalDate(getDecisionSignalPresentation(item).timestamp)?.getTime() ?? 0;
}

export function isNewerSignal(left: DecisionSignalItem | undefined, right: DecisionSignalItem): boolean {
  if (!left) return true;
  return getSignalTime(right) > getSignalTime(left);
}

export function formatPortfolioLimitation(limitation: string, language: UiLanguage): string {
  return PORTFOLIO_LIMITATION_LABELS[language][limitation] ?? limitation;
}

export function toDecisionSignalMarket(value: string | null | undefined): DecisionSignalMarket | undefined {
  const normalized = String(value || '').toLowerCase();
  return DECISION_SIGNAL_MARKETS.has(normalized as DecisionSignalMarket)
    ? normalized as DecisionSignalMarket
    : undefined;
}

export function toPositionSignalLookupKey(stockCode: string, market?: DecisionSignalMarket): string {
  return `${market || ''}:${normalizeStockCode(stockCode).toUpperCase()}`;
}

export async function mapWithConcurrency<T, R>(
  items: T[],
  concurrency: number,
  mapper: (item: T) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let nextIndex = 0;
  const workerCount = Math.min(Math.max(1, concurrency), items.length);

  await Promise.all(Array.from({ length: workerCount }, async () => {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex;
      nextIndex += 1;
      results[currentIndex] = await mapper(items[currentIndex]);
    }
  }));

  return results;
}

export async function loadPortfolioSignalLookup(lookup: PortfolioSignalLookup): Promise<PortfolioSignalLookupResult> {
  try {
    const response = await decisionSignalsApi.getLatest(lookup.stockCode, {
      market: lookup.market,
      limit: 1,
    });
    return { items: response.items, error: null };
  } catch (err) {
    return { items: [], error: getParsedApiError(err).message };
  }
}
