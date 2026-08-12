// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import type { ParsedApiError } from '../../api/error';
import type { DecisionSignalOutcomeStatsResponse } from '../../types/decisionSignals';
import { DecisionSignalOutcomeExplorer } from './DecisionSignalOutcomeExplorer';
import { DecisionSignalOutcomeStatsCard } from './DecisionSignalOutcomeStatsCard';

export type DecisionSignalReviewSectionProps = {
  stats: DecisionSignalOutcomeStatsResponse | null;
  loading: boolean;
  error: ParsedApiError | null;
  onRetryStats: () => void;
  outcomeExplorerRefreshKey: number;
  onOpenSignal: (signalId: number) => void;
  onOutcomeRunCompleted: () => void;
  showExplorer: boolean;
};

/**
 * Signal Center Review tab: production host for outcome stats + explorer.
 * Stats chrome lives in DecisionSignalOutcomeStatsCard so the card is not
 * Playground-only; this section owns tab-level composition only.
 */
const DecisionSignalReviewSection: React.FC<DecisionSignalReviewSectionProps> = ({
  stats,
  loading,
  error,
  onRetryStats,
  outcomeExplorerRefreshKey,
  onOpenSignal,
  onOutcomeRunCompleted,
  showExplorer,
}) => (
  <>
    <DecisionSignalOutcomeStatsCard
      outcomeStats={stats}
      statsLoading={loading}
      statsError={error}
      onRetryStats={onRetryStats}
      onRunCompleted={onOutcomeRunCompleted}
    />
    {showExplorer ? (
      <DecisionSignalOutcomeExplorer
        refreshKey={outcomeExplorerRefreshKey}
        onOpenSignal={onOpenSignal}
      />
    ) : null}
  </>
);

export default DecisionSignalReviewSection;
