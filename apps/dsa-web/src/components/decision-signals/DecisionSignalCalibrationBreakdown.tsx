// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo, useState } from 'react';
import type { DecisionAction } from '../../types/analysis';
import type {
  DecisionSignalMarket,
  DecisionSignalOutcomeStatsBucket,
  DecisionSignalOutcomeStatsResponse,
} from '../../types/decisionSignals';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { buildDecisionActionLabelMap } from '../../utils/decisionAction';
import { cn } from '../../utils/cn';
import { Badge } from '../common';

type CalibrationGroup = 'period' | 'market' | 'action';

const GROUP_ORDER: CalibrationGroup[] = ['period', 'market', 'action'];

const ACTION_VALUES: DecisionAction[] = [
  'buy', 'add', 'hold', 'reduce', 'sell', 'watch', 'avoid', 'alert',
];
const MARKET_VALUES: DecisionSignalMarket[] = ['cn', 'hk', 'us', 'jp', 'kr', 'tw'];

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '';
  const formatted = Number(value).toFixed(2).replace(/\.?0+$/, '');
  return `${formatted}%`;
}

function isDecisionAction(value: string): value is DecisionAction {
  return ACTION_VALUES.includes(value as DecisionAction);
}

function isDecisionSignalMarket(value: string): value is DecisionSignalMarket {
  return MARKET_VALUES.includes(value as DecisionSignalMarket);
}

type Props = {
  stats: DecisionSignalOutcomeStatsResponse;
};

/**
 * Process-quality calibration groupings for DecisionSignal post-hoc outcomes.
 * Consumes already-evaluated outcome stats; does not re-score prices.
 */
export const DecisionSignalCalibrationBreakdown: React.FC<Props> = ({ stats }) => {
  const { t } = useUiLanguage();
  const actionLabels = useMemo(() => buildDecisionActionLabelMap(t), [t]);
  const [group, setGroup] = useState<CalibrationGroup>('period');

  const buckets: DecisionSignalOutcomeStatsBucket[] = stats.breakdowns[group] ?? [];
  const minSamples = stats.minimumCompletedSampleSize ?? 30;

  const labelFor = (bucket: DecisionSignalOutcomeStatsBucket): string => {
    if (group === 'action') {
      return isDecisionAction(bucket.value)
        ? actionLabels[bucket.value]
        : t('decisionSignals.calibrationUnknownValue');
    }
    if (group === 'market') {
      if (isDecisionSignalMarket(bucket.value)) {
        return t(`decisionSignals.market.${bucket.value}`);
      }
      return bucket.value === 'unknown'
        ? t('decisionSignals.calibrationUnknownValue')
        : bucket.value.toUpperCase();
    }
    // period YYYY-MM
    if (bucket.value === 'unknown') {
      return t('decisionSignals.calibrationUnknownValue');
    }
    return bucket.value;
  };

  const groupLabel = (mode: CalibrationGroup): string => {
    if (mode === 'period') return t('decisionSignals.calibrationByPeriod');
    if (mode === 'market') return t('decisionSignals.calibrationByMarket');
    return t('decisionSignals.calibrationBySignalType');
  };

  return (
    <section
      className="mt-5 border-t border-border/60 pt-5"
      aria-labelledby="decision-signal-calibration-title"
      data-testid="decision-signal-calibration-breakdown"
    >
      <div className="max-w-3xl">
        <h3
          id="decision-signal-calibration-title"
          className="text-base font-semibold text-foreground"
        >
          {t('decisionSignals.calibrationTitle')}
        </h3>
        <p className="mt-1 text-sm text-secondary-text">
          {t('decisionSignals.calibrationDescription')}
        </p>
        <p className="mt-1 text-xs text-secondary-text">
          {t('decisionSignals.calibrationThreshold', { count: minSamples })}
        </p>
      </div>

      <div
        className="mt-4 flex flex-wrap gap-2"
        role="group"
        aria-label={t('decisionSignals.calibrationGroupLabel')}
      >
        {GROUP_ORDER.map((mode) => {
          const selected = group === mode;
          return (
            <button
              key={mode}
              type="button"
              aria-pressed={selected}
              onClick={() => setGroup(mode)}
              className={cn(
                'rounded-lg border px-3 py-2 text-sm transition-colors',
                selected
                  ? 'border-primary/70 bg-primary/10 text-foreground'
                  : 'border-border/60 text-secondary-text hover:border-primary/40 hover:text-foreground',
              )}
            >
              {groupLabel(mode)}
            </button>
          );
        })}
      </div>

      {buckets.length === 0 ? (
        <p className="mt-3 text-sm text-secondary-text">
          {t('decisionSignals.calibrationNoBuckets')}
        </p>
      ) : (
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          {buckets.map((bucket) => {
            const label = labelFor(bucket);
            const sufficient = bucket.sampleSufficient === true;
            return (
              <article
                key={`${group}-${bucket.value}`}
                className="rounded-xl border border-border/60 bg-elevated/25 p-4"
                data-testid={`calibration-bucket-${group}-${bucket.value}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-sm font-semibold text-foreground">{label}</h4>
                  <Badge variant={sufficient ? 'success' : 'history'} size="sm">
                    {sufficient
                      ? t('decisionSignals.calibrationSampleSufficient')
                      : t('decisionSignals.calibrationSampleInsufficient')}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-secondary-text">
                  {t('decisionSignals.calibrationSampleCounts', {
                    completed: bucket.completed,
                    total: bucket.total,
                  })}
                </p>
                {!sufficient ? (
                  <p
                    className="mt-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning"
                    role="status"
                  >
                    {t('decisionSignals.calibrationInsufficientNotice')}
                  </p>
                ) : (
                  <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                    <div className="rounded-lg border border-border/50 bg-background/30 px-3 py-2">
                      <p className="text-xs text-secondary-text">
                        {t('decisionSignals.statsHitRate')}
                      </p>
                      <p className="mt-1 text-base font-semibold text-success">
                        {formatPercent(bucket.hitRatePct)
                          || t('decisionSignals.calibrationRateUnavailable')}
                      </p>
                    </div>
                    <div className="rounded-lg border border-border/50 bg-background/30 px-3 py-2">
                      <p className="text-xs text-secondary-text">
                        {t('decisionSignals.outcome.hit')}
                      </p>
                      <p className="mt-1 text-base font-semibold text-foreground">
                        {bucket.hit}
                      </p>
                    </div>
                    <div className="rounded-lg border border-border/50 bg-background/30 px-3 py-2">
                      <p className="text-xs text-secondary-text">
                        {t('decisionSignals.outcome.miss')}
                      </p>
                      <p className="mt-1 text-base font-semibold text-foreground">
                        {bucket.miss}
                      </p>
                    </div>
                  </div>
                )}
                {/* Counts remain visible even when rates are gated. */}
                {!sufficient ? (
                  <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-secondary-text">
                    <span>{t('decisionSignals.outcome.hit')}: {bucket.hit}</span>
                    <span>{t('decisionSignals.outcome.miss')}: {bucket.miss}</span>
                    <span>{t('decisionSignals.outcome.unable')}: {bucket.unable}</span>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
};

export default DecisionSignalCalibrationBreakdown;
