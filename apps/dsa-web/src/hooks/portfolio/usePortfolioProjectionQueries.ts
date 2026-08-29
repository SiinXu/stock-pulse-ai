// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// TanStack Query keys and snapshot-then-risk fetcher for the Portfolio projection session.

import { CancelledError } from '@tanstack/react-query';
import { portfolioApi } from '../../api/portfolio';
import { getParsedApiError } from '../../api/error';
import type { UiLanguage } from '../../i18n/uiText';
import type {
  PortfolioCostMethod,
  PortfolioRiskResponse,
  PortfolioSnapshotResponse,
} from '../../types/portfolio';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const PORTFOLIO_PROJECTION_CANCEL = { silent: true, revert: false } as const;

export const PORTFOLIO_PROJECTION_SNAPSHOT_QUERY_KEY_ROOT = [
  'portfolio',
  'projection',
  'snapshot-risk',
] as const;

/** Previous snapshot/risk effects never polled, never focus-refetched, and never retried. */
export const PORTFOLIO_PROJECTION_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
} as const;

export type PortfolioSnapshotRiskQueryData = {
  snapshot: PortfolioSnapshotResponse;
  risk: PortfolioRiskResponse | null;
  riskWarning: string | null;
};

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

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfProjectionCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
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
      riskWarning:
        getParsedApiError(riskError, args.language).message || args.riskFallbackMessage,
    };
  }
}
