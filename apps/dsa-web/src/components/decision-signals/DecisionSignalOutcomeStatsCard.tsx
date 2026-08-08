// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { BarChart3 } from 'lucide-react';
import type { ParsedApiError } from '../../api/error';
import type { DecisionSignalOutcomeStatsResponse } from '../../types/decisionSignals';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import {
  ApiErrorAlert,
  Badge,
  Card,
  EmptyState,
  Loading,
  StatCard,
} from '../common';
import { DecisionSignalOutcomeRunPanel } from './DecisionSignalOutcomeRunPanel';
import { DecisionSignalProfileCalibration } from './DecisionSignalProfileCalibration';

function formatStatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  const formatted = Number(value).toFixed(2).replace(/\.?0+$/, '');
  return `${formatted}%`;
}

type Props = {
  outcomeStats: DecisionSignalOutcomeStatsResponse | null;
  statsLoading: boolean;
  statsError: ParsedApiError | null;
  onRetryStats: () => void;
  onRunCompleted: () => void;
};

export const DecisionSignalOutcomeStatsCard: React.FC<Props> = ({
  outcomeStats,
  statsLoading,
  statsError,
  onRetryStats,
  onRunCompleted,
}) => {
  const { t } = useUiLanguage();

  return (
    <Card
      title={t('decisionSignals.statsTitle')}
      subtitle={t('decisionSignals.statsDescription')}
      padding="md"
      headerRight={<Badge variant="default" size="sm">{t('decisionSignals.scopeGlobal')}</Badge>}
    >
      <p className="mb-3 text-sm text-secondary-text">{t('decisionSignals.statsGlobalScope')}</p>
      {statsError ? (
        <ApiErrorAlert
          error={{ ...statsError, title: t('decisionSignals.statsErrorTitle') }}
          actionLabel={t('common.retry')}
          onAction={onRetryStats}
        />
      ) : statsLoading ? (
        <Loading />
      ) : outcomeStats && outcomeStats.total > 0 ? (
        <div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard label={t('decisionSignals.statsTotal')} value={outcomeStats.total} />
            <StatCard
              tone="success"
              label={t('decisionSignals.statsHitRate')}
              value={<span className="text-success">{formatStatPercent(outcomeStats.hitRatePct)}</span>}
            />
            <StatCard
              tone="success"
              label={t('decisionSignals.outcome.hit')}
              value={<span className="text-success">{outcomeStats.hit}</span>}
            />
            <StatCard
              tone="danger"
              label={t('decisionSignals.outcome.miss')}
              value={<span className="text-danger">{outcomeStats.miss}</span>}
            />
            <StatCard
              tone="warning"
              label={t('decisionSignals.outcome.unable')}
              value={<span className="text-warning">{outcomeStats.unable}</span>}
            />
          </div>
          {outcomeStats.profileCalibration ? (
            <DecisionSignalProfileCalibration calibration={outcomeStats.profileCalibration} />
          ) : null}
        </div>
      ) : (
        <EmptyState
          compact
          title={t('decisionSignals.noReviewedStatsTitle')}
          description={t('decisionSignals.noReviewedStatsDescription')}
          icon={<BarChart3 className="h-6 w-6" />}
        />
      )}
      <DecisionSignalOutcomeRunPanel onCompleted={onRunCompleted} />
    </Card>
  );
};
