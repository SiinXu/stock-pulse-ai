// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery } from '@tanstack/react-query';
import { getPortfolioRiskMetrics } from '../../api/portfolioRiskMetrics';
import type { PortfolioRiskMetricsQuery } from '../../types/portfolioRiskMetrics';

export const PORTFOLIO_RISK_METRICS_QUERY_KEY_ROOT = ['portfolio', 'risk-metrics'] as const;

export function buildPortfolioRiskMetricsQueryKey(
  input: PortfolioRiskMetricsQuery,
): readonly unknown[] {
  return [
    ...PORTFOLIO_RISK_METRICS_QUERY_KEY_ROOT,
    input.accountId ?? 'all',
    input.asOf ?? 'today',
    input.costMethod ?? 'fifo',
    input.confidence ?? 'default',
    input.horizonDays ?? 'default',
    input.lookbackTradingDays ?? 'default',
  ] as const;
}

export type UsePortfolioRiskMetricsQueryOptions = PortfolioRiskMetricsQuery & {
  enabled?: boolean;
};

/**
 * TanStack Query schedule for portfolio risk-metrics.
 * No focus refetch; matches other portfolio-adjacent read schedules.
 */
export function usePortfolioRiskMetricsQuery(options: UsePortfolioRiskMetricsQueryOptions = {}) {
  const {
    enabled = true,
    accountId,
    asOf,
    costMethod,
    confidence,
    horizonDays,
    lookbackTradingDays,
  } = options;

  const query: PortfolioRiskMetricsQuery = {
    accountId,
    asOf,
    costMethod,
    confidence,
    horizonDays,
    lookbackTradingDays,
  };

  return useQuery({
    queryKey: buildPortfolioRiskMetricsQueryKey(query),
    enabled,
    queryFn: () => getPortfolioRiskMetrics(query),
    retry: false,
    refetchOnWindowFocus: false,
  });
}
