// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { ArrowRight, BellRing } from 'lucide-react';
import { Button, Section, StatePanel } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

export type HomeSignalSummaryAvailability = {
  activeSignals: boolean;
  reassessments: boolean;
  alerts: boolean;
};

export type HomeSignalSummaryTotals = {
  activeSignalTotal: number | null;
  triggeredAlertTotal: number | null;
  dueReassessmentTotal: number | null;
};

export type HomeSignalSummaryStale = {
  activeSignals: boolean;
  reassessments: boolean;
  alerts: boolean;
};

export type HomeSignalSummaryProps = {
  isLoading: boolean;
  availability: HomeSignalSummaryAvailability;
  data: HomeSignalSummaryTotals;
  stale: HomeSignalSummaryStale;
  onRetry: () => void;
  onViewAll: () => void;
};

export const HomeSignalSummary: React.FC<HomeSignalSummaryProps> = ({
  isLoading,
  availability,
  data,
  stale,
  onRetry,
  onViewAll,
}) => {
  const { t } = useUiLanguage();
  const hasSnapshot = data.activeSignalTotal !== null
    || data.triggeredAlertTotal !== null
    || data.dueReassessmentTotal !== null;
  const anyAvailable = availability.activeSignals
    || availability.reassessments
    || availability.alerts;
  const anyFailed = !availability.activeSignals
    || !availability.reassessments
    || !availability.alerts;
  const anyStale = stale.activeSignals || stale.reassessments || stale.alerts;
  const retryAction = (
    <Button variant="secondary" size="default" onClick={onRetry}>
      {t('common.retry')}
    </Button>
  );

  return (
    <Section
      title={t('home.signalSummary')}
      description={t('home.signalSummaryDescription')}
      level="interactive"
      padding="md"
      actions={<BellRing className="h-5 w-5 text-danger" aria-hidden="true" />}
      data-testid="home-signal-summary"
    >
      {isLoading && !hasSnapshot ? (
        <StatePanel state="loading" title={t('common.loading')} size="compact" />
      ) : !isLoading && !anyAvailable && !hasSnapshot ? (
        <StatePanel
          state="error"
          title={t('home.partialDataTitle')}
          description={t('home.partialDataMessage')}
          action={retryAction}
          size="compact"
        />
      ) : (
        <div className="space-y-4">
          {isLoading ? (
            <StatePanel
              state="retrying"
              title={t('common.loading')}
              size="compact"
              titleAs="p"
            />
          ) : anyFailed ? (
            <StatePanel
              state={anyStale || anyAvailable ? 'partial' : 'error'}
              title={t('home.partialDataTitle')}
              description={t('home.partialDataMessage')}
              action={retryAction}
              size="compact"
              titleAs="p"
            />
          ) : null}
          <dl className="grid grid-cols-3 gap-3">
            <HomeSignalMetric
              label={t('home.activeSignals')}
              value={data.activeSignalTotal}
              available={availability.activeSignals}
              stale={stale.activeSignals}
            />
            <HomeSignalMetric
              label={t('home.triggeredAlerts')}
              value={data.triggeredAlertTotal}
              available={availability.alerts}
              stale={stale.alerts}
            />
            <HomeSignalMetric
              label={t('home.dueReassessments')}
              value={data.dueReassessmentTotal}
              available={availability.reassessments}
              stale={stale.reassessments}
            />
          </dl>
          <Button className="mx-auto" variant="secondary" size="default" onClick={onViewAll}>
            {t('decisionSignals.viewAll')}
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      )}
    </Section>
  );
};

function HomeSignalMetric({
  label,
  value,
  available,
  stale,
}: {
  label: string;
  value: number | null;
  available: boolean;
  stale: boolean;
}) {
  const { t } = useUiLanguage();
  const showLastKnown = value !== null && (available || stale);
  return (
    <div
      data-testid="home-signal-metric"
      data-available={available ? 'true' : 'false'}
      data-stale={stale ? 'true' : 'false'}
    >
      <dt className="text-xs text-secondary-text">{label}</dt>
      <dd className="mt-1 text-xl font-semibold tabular-nums text-foreground">
        {showLastKnown ? (
          <>
            {value}
            {stale ? (
              <span className="ml-1 text-xs font-medium text-warning">{t('common.partial')}</span>
            ) : null}
          </>
        ) : (
          <span className="text-sm font-medium text-danger" data-testid="home-signal-metric-failure">
            {t('common.failure')}
          </span>
        )}
      </dd>
    </div>
  );
}

export default HomeSignalSummary;
