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
  InlineAlert,
  Loading,
  StatCard,
} from '../common';
import { DecisionSignalCalibrationBreakdown } from './DecisionSignalCalibrationBreakdown';
import { DecisionSignalOutcomeRunPanel } from './DecisionSignalOutcomeRunPanel';
import { DecisionSignalProfileCalibration } from './DecisionSignalProfileCalibration';

function formatStatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
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
  const minSamples = outcomeStats?.minimumCompletedSampleSize ?? 30;
  const sampleSufficient = outcomeStats?.sampleSufficient === true;

  return (
    <Card
      title={t('decisionSignals.statsTitle')}
      subtitle={t('decisionSignals.statsDescription')}
      padding="md"
      headerRight={<Badge variant="default" size="sm">{t('decisionSignals.scopeGlobal')}</Badge>}
    >
      {/* Research-tool positioning: process quality, not return promises. */}
      <InlineAlert
        variant="info"
        className="mb-3"
        title={t('decisionSignals.researchPositionTitle')}
        message={t('decisionSignals.researchPositionBody')}
        data-testid="decision-signal-research-position"
      />
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
          {!sampleSufficient ? (
            <p
              className="mb-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning"
              role="status"
              data-testid="decision-signal-sample-insufficient"
            >
              {t('decisionSignals.statsInsufficientNotice', { count: minSamples })}
            </p>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard label={t('decisionSignals.statsTotal')} value={outcomeStats.total} />
            <StatCard
              tone="success"
              label={t('decisionSignals.statsHitRate')}
              value={(
                <span className="text-success">
                  {sampleSufficient
                    ? formatStatPercent(outcomeStats.hitRatePct)
                    : t('decisionSignals.statsRateHidden')}
                </span>
              )}
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
          <DecisionSignalCalibrationBreakdown stats={outcomeStats} />
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
