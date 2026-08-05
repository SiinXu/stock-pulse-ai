// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { BarChart3 } from 'lucide-react';
import type { ParsedApiError } from '../../api/error';
import {
  ApiErrorAlert,
  Badge,
  Card,
  EmptyState,
  Loading,
  StatCard,
} from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { DecisionSignalOutcomeStatsResponse } from '../../types/decisionSignals';
import { DecisionSignalOutcomeExplorer } from './DecisionSignalOutcomeExplorer';
import { DecisionSignalOutcomeRunPanel } from './DecisionSignalOutcomeRunPanel';
import { formatStatPercent } from './decisionSignalsPageModel';

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

const DecisionSignalReviewSection: React.FC<DecisionSignalReviewSectionProps> = ({
  stats,
  loading,
  error,
  onRetryStats,
  outcomeExplorerRefreshKey,
  onOpenSignal,
  onOutcomeRunCompleted,
  showExplorer,
}) => {
  const { t } = useUiLanguage();

  return (
    <>
      <Card
        title={t('decisionSignals.statsTitle')}
        subtitle={t('decisionSignals.statsDescription')}
        padding="md"
        headerRight={<Badge variant="default" size="sm">{t('decisionSignals.scopeGlobal')}</Badge>}
      >
        <p className="mb-3 text-sm text-secondary-text">{t('decisionSignals.statsGlobalScope')}</p>
        {error ? (
          <ApiErrorAlert
            error={{ ...error, title: t('decisionSignals.statsErrorTitle') }}
            actionLabel={t('common.retry')}
            onAction={onRetryStats}
          />
        ) : loading ? (
          <Loading />
        ) : stats && stats.total > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard label={t('decisionSignals.statsTotal')} value={stats.total} />
            <StatCard
              tone="success"
              label={t('decisionSignals.statsHitRate')}
              value={<span className="text-success">{formatStatPercent(stats.hitRatePct)}</span>}
            />
            <StatCard
              tone="success"
              label={t('decisionSignals.outcome.hit')}
              value={<span className="text-success">{stats.hit}</span>}
            />
            <StatCard
              tone="danger"
              label={t('decisionSignals.outcome.miss')}
              value={<span className="text-danger">{stats.miss}</span>}
            />
            <StatCard
              tone="warning"
              label={t('decisionSignals.outcome.unable')}
              value={<span className="text-warning">{stats.unable}</span>}
            />
          </div>
        ) : (
          <EmptyState
            compact
            title={t('decisionSignals.noReviewedStatsTitle')}
            description={t('decisionSignals.noReviewedStatsDescription')}
            icon={<BarChart3 className="h-6 w-6" />}
          />
        )}
        <DecisionSignalOutcomeRunPanel onCompleted={onOutcomeRunCompleted} />
      </Card>
      {showExplorer ? (
        <DecisionSignalOutcomeExplorer
          refreshKey={outcomeExplorerRefreshKey}
          onOpenSignal={onOpenSignal}
        />
      ) : null}
    </>
  );
};

export default DecisionSignalReviewSection;
