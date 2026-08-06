// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Feature-private holding-signal projection for the Portfolio route.

import { useEffect, useMemo, useRef, useState } from 'react';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import { formatUiText } from '../../i18n/uiText';
import { areStockCodesEquivalent } from '../../utils/stockCode';
import {
  isNewerSignal,
  loadPortfolioSignalLookup,
  mapWithConcurrency,
  toDecisionSignalMarket,
  toPositionSignalLookupKey,
  type PortfolioSignalLookup,
} from './helpers';
import { PORTFOLIO_SIGNAL_LOOKUP_CONCURRENCY } from './constants';
import type { FlatPosition } from './types';

type UsePortfolioHoldingSignalsOptions = {
  positionRows: FlatPosition[];
  snapshotMatchesAccountScope: boolean;
  paperTradeProjectionRevision: number;
  // Structural match for useUiLanguage().t without importing the full key union.
  t: (key: 'decisionSignals.portfolioPartialWarning', params?: { message: string }) => string;
};

export function usePortfolioHoldingSignals({
  positionRows,
  snapshotMatchesAccountScope,
  paperTradeProjectionRevision,
  t,
}: UsePortfolioHoldingSignalsOptions) {
  const [portfolioSignals, setPortfolioSignals] = useState<DecisionSignalItem[]>([]);
  const [portfolioSignalsLoading, setPortfolioSignalsLoading] = useState(false);
  const [portfolioSignalsWarning, setPortfolioSignalsWarning] = useState<string | null>(null);
  const [portfolioSignalsRefreshKey, setPortfolioSignalsRefreshKey] = useState(0);
  const portfolioSignalsRequestRef = useRef(0);

  const positionSignalLookups = useMemo(() => {
    const lookups = new Map<string, PortfolioSignalLookup>();
    for (const row of positionRows) {
      const stockCode = String(row.symbol || '').trim();
      if (!stockCode) continue;
      const market = toDecisionSignalMarket(row.market);
      const key = toPositionSignalLookupKey(stockCode, market);
      if (!lookups.has(key)) {
        lookups.set(key, { stockCode, market });
      }
    }
    return Array.from(lookups.values());
  }, [positionRows]);

  useEffect(() => {
    const requestId = portfolioSignalsRequestRef.current + 1;
    portfolioSignalsRequestRef.current = requestId;

    if (positionSignalLookups.length === 0 || !snapshotMatchesAccountScope) {
      // Request-scoped reset when the holding set or account scope is empty.
      // Preserves the prior PortfolioPage effect contract (clear stale signals).
      /* eslint-disable react-hooks/set-state-in-effect -- intentional scope reset */
      setPortfolioSignals([]);
      setPortfolioSignalsWarning(null);
      setPortfolioSignalsLoading(false);
      /* eslint-enable react-hooks/set-state-in-effect */
      return;
    }

    const isActiveRequest = () => portfolioSignalsRequestRef.current === requestId;

    const loadPortfolioSignals = async () => {
      setPortfolioSignalsLoading(true);
      setPortfolioSignalsWarning(null);
      const results = await mapWithConcurrency(
        positionSignalLookups,
        PORTFOLIO_SIGNAL_LOOKUP_CONCURRENCY,
        loadPortfolioSignalLookup,
      );
      if (!isActiveRequest()) return;
      const collected = results.flatMap((result) => result.items);
      const failures = results.flatMap((result) => (result.error ? [result.error] : []));
      setPortfolioSignals(collected);
      setPortfolioSignalsWarning(
        failures.length > 0
          ? (
              collected.length > 0
                ? formatUiText(t('decisionSignals.portfolioPartialWarning'), { message: failures[0] })
                : failures[0]
            )
          : null,
      );
      if (isActiveRequest()) {
        setPortfolioSignalsLoading(false);
      }
    };

    void loadPortfolioSignals();

    return () => {
      portfolioSignalsRequestRef.current += 1;
    };
  }, [
    paperTradeProjectionRevision,
    portfolioSignalsRefreshKey,
    positionSignalLookups,
    snapshotMatchesAccountScope,
    t,
  ]);

  const signalByPositionKey = useMemo(() => {
    const mapped = new Map<string, DecisionSignalItem>();
    for (const row of positionRows) {
      const rowMarket = String(row.market || '').toLowerCase();
      for (const signal of portfolioSignals) {
        const signalMarket = String(signal.market || '').toLowerCase();
        if (rowMarket && signalMarket && rowMarket !== signalMarket) {
          continue;
        }
        if (!areStockCodesEquivalent(row.symbol, signal.stockCode)) {
          continue;
        }
        const key = `${row.accountId}-${row.symbol}-${row.market}`;
        const existing = mapped.get(key);
        if (isNewerSignal(existing, signal)) {
          mapped.set(key, signal);
        }
      }
    }
    return mapped;
  }, [portfolioSignals, positionRows]);

  const bumpSignalsRefresh = () => {
    setPortfolioSignalsRefreshKey((current) => current + 1);
  };

  return {
    portfolioSignalsLoading,
    portfolioSignalsWarning,
    signalByPositionKey,
    bumpSignalsRefresh,
  };
}
