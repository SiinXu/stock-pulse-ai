// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useMemo, useState } from 'react';
import type React from 'react';
import { RefreshCw } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { scorecardApi } from '../../api/scorecard';
import type {
  ScorecardBucket,
  ScorecardMiss,
  ScorecardReturnBand,
  SignalScorecardResponse,
} from '../../types/scorecard';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import { getUiLocale } from '../../utils/uiLocale';
import {
  ApiErrorAlert,
  Badge,
  DataTable,
  type DataTableColumn,
  EmptyState,
  IconButton,
  StatePanel,
  Surface,
} from '../common';
import { SettingsSectionCard } from './SettingsSectionCard';

type SignalScorecardPanelProps = {
  /** Effective public-enable flag from the settings config pipeline. */
  publicEnabled: boolean;
  /** Effective min-samples value shown for operator context. */
  minSamples: number | null;
  disabled?: boolean;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  language: UiLanguage;
};

function formatPct(value: number | null | undefined, language: UiLanguage): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return `${value.toLocaleString(getUiLocale(language), {
    maximumFractionDigits: 1,
    minimumFractionDigits: 0,
  })}%`;
}

function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return String(value);
}

function isDisabledScorecardError(error: ParsedApiError | null): boolean {
  if (!error) return false;
  return error.status === 404 || error.code === 'not_found';
}

const SignalScorecardPanel: React.FC<SignalScorecardPanelProps> = ({
  publicEnabled,
  minSamples,
  disabled = false,
  t,
  language,
}) => {
  const [data, setData] = useState<SignalScorecardResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);

  const loadScorecard = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    // Preview uses the public route only. When the Settings draft flag is off,
    // do not call the endpoint (default-off stays quiet and fail-closed).
    if (!publicEnabled) {
      setData(null);
      setLoadError(null);
      setIsLoading(false);
      setIsRefreshing(false);
      return;
    }

    setLoadError(null);
    if (mode === 'initial') {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }
    try {
      const next = await scorecardApi.getPublic();
      setData(next);
    } catch (error: unknown) {
      setData(null);
      setLoadError(getParsedApiError(error));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [publicEnabled]);

  useEffect(() => {
    void loadScorecard('initial');
  }, [loadScorecard]);

  const disabledByApi = isDisabledScorecardError(loadError);
  const showDisabled = !publicEnabled || disabledByApi;
  const showApiError = Boolean(loadError && !disabledByApi);
  const overall = data?.overall;
  const hasBuckets = Boolean(data?.bySignalTypeHorizon?.length);
  const hasDistribution = Boolean(data?.returnDistribution?.length);
  const hasMisses = Boolean(data?.recentMisses?.length);
  const hasAggregateContent = hasBuckets || hasDistribution || hasMisses;

  const statusBadge = useMemo(() => {
    if (publicEnabled && !disabledByApi) {
      return (
        <Badge variant="success" size="sm">
          {t('settings.scorecardStatusEnabled')}
        </Badge>
      );
    }
    return (
      <Badge variant="history" size="sm">
        {t('settings.scorecardStatusDisabled')}
      </Badge>
    );
  }, [disabledByApi, publicEnabled, t]);

  const bucketColumns = useMemo<DataTableColumn<ScorecardBucket>[]>(() => [
    {
      id: 'signalType',
      header: t('settings.scorecardSignalType'),
      cell: (bucket) => bucket.signalType || '—',
    },
    {
      id: 'horizon',
      header: t('settings.scorecardHorizon'),
      cell: (bucket) => bucket.horizon || '—',
    },
    {
      id: 'sampleSize',
      header: t('settings.scorecardSampleSize'),
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text">{formatCount(bucket.sampleSize)}</span>
      ),
    },
    {
      id: 'hitRate',
      header: t('settings.scorecardHitRate'),
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text">
          {bucket.status !== 'ok'
            ? t('settings.scorecardInsufficient')
            : formatPct(bucket.hitRatePct, language)}
        </span>
      ),
    },
    {
      id: 'avgReturn',
      header: t('settings.scorecardAvgReturn'),
      cell: (bucket) => (
        <span className="tabular-nums text-muted-text">
          {bucket.status !== 'ok' ? '—' : formatPct(bucket.avgReturnPct, language)}
        </span>
      ),
    },
  ], [language, t]);

  const distributionColumns = useMemo<DataTableColumn<ScorecardReturnBand>[]>(() => [
    {
      id: 'band',
      header: t('settings.scorecardBand'),
      cell: (band) => band.band,
    },
    {
      id: 'count',
      header: t('settings.scorecardCount'),
      cell: (band) => (
        <span className="tabular-nums text-muted-text">{formatCount(band.count)}</span>
      ),
    },
    {
      id: 'share',
      header: t('settings.scorecardShare'),
      cell: (band) => (
        <span className="tabular-nums text-muted-text">{formatPct(band.sharePct, language)}</span>
      ),
    },
  ], [language, t]);

  const missColumns = useMemo<DataTableColumn<ScorecardMiss>[]>(() => [
    {
      id: 'signalType',
      header: t('settings.scorecardSignalType'),
      cell: (miss) => miss.signalType || '—',
    },
    {
      id: 'horizon',
      header: t('settings.scorecardHorizon'),
      cell: (miss) => miss.horizon || '—',
    },
    {
      id: 'return',
      header: t('settings.scorecardAvgReturn'),
      cell: (miss) => (
        <span className="tabular-nums text-muted-text">{formatPct(miss.returnPct, language)}</span>
      ),
    },
    {
      id: 'anchorDate',
      header: t('settings.scorecardAnchorDate'),
      cell: (miss) => (
        <span className="text-muted-text">{miss.anchorDate || '—'}</span>
      ),
    },
  ], [language, t]);

  return (
    <SettingsSectionCard
      title={t('settings.scorecardTitle')}
      description={t('settings.scorecardDescription')}
      actions={(
        <IconButton
          type="button"
          variant="ghost"
          size="compact"
          aria-label={t('settings.scorecardRefreshAria')}
          disabled={disabled || isLoading || isRefreshing || !publicEnabled}
          onClick={() => void loadScorecard('refresh')}
        >
          <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} aria-hidden="true" />
        </IconButton>
      )}
      contentBordered
    >
      <div className="space-y-4">
        <Surface level="interactive" className="flex flex-col gap-2 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-text">
              {t('settings.scorecardStatusLabel')}
            </span>
            {statusBadge}
            {minSamples !== null ? (
              <Badge variant="default" size="sm">
                {t('settings.scorecardMinSamplesLabel')}: {minSamples}
              </Badge>
            ) : null}
          </div>
          <p className="text-xs leading-5 text-muted-text">
            {t('settings.scorecardPublicNote')}
          </p>
        </Surface>

        {isLoading ? (
          <StatePanel
            state="loading"
            title={t('settings.scorecardTitle')}
            description={t('common.loading')}
          />
        ) : null}

        {!isLoading && showDisabled ? (
          <EmptyState
            title={t('settings.scorecardDisabledTitle')}
            description={t('settings.scorecardDisabledDescription')}
          />
        ) : null}

        {!isLoading && showApiError && loadError ? (
          <ApiErrorAlert error={loadError} />
        ) : null}

        {!isLoading && publicEnabled && !disabledByApi && !showApiError && data ? (
          <>
            <Surface level="interactive" className="grid grid-cols-2 gap-3 px-4 py-3 md:grid-cols-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-text">
                  {t('settings.scorecardOverall')}
                </p>
                <p className="mt-1 text-sm font-semibold text-foreground">
                  {overall?.status === 'ok'
                    ? formatPct(overall.hitRatePct, language)
                    : t('settings.scorecardInsufficient')}
                </p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-text">
                  {t('settings.scorecardSampleSize')}
                </p>
                <p className="mt-1 text-sm tabular-nums text-foreground">
                  {formatCount(overall?.sampleSize)}
                </p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-text">
                  {t('settings.scorecardCompleted')}
                </p>
                <p className="mt-1 text-sm tabular-nums text-foreground">
                  {formatCount(overall?.completed)}
                </p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-text">
                  {t('settings.scorecardAvgReturn')}
                </p>
                <p className="mt-1 text-sm tabular-nums text-foreground">
                  {overall?.status === 'ok'
                    ? formatPct(overall.avgReturnPct, language)
                    : '—'}
                </p>
              </div>
            </Surface>

            {!hasAggregateContent ? (
              <EmptyState
                title={t('settings.scorecardEmptyTitle')}
                description={t('settings.scorecardEmptyDescription')}
              />
            ) : null}

            {hasBuckets ? (
              <DataTable
                caption={t('settings.scorecardByTypeHorizon')}
                frame="embedded"
                density="compact"
                columns={bucketColumns}
                rows={data.bySignalTypeHorizon}
                getRowKey={(bucket) => `${bucket.signalType}:${bucket.horizon}`}
                emptyState={{
                  title: t('settings.scorecardEmptyTitle'),
                  description: t('settings.scorecardEmptyDescription'),
                }}
              />
            ) : null}

            {hasDistribution ? (
              <DataTable
                caption={t('settings.scorecardReturnDistribution')}
                frame="embedded"
                density="compact"
                columns={distributionColumns}
                rows={data.returnDistribution}
                getRowKey={(band) => band.band}
                emptyState={{
                  title: t('settings.scorecardEmptyTitle'),
                  description: t('settings.scorecardEmptyDescription'),
                }}
              />
            ) : null}

            {hasMisses ? (
              <DataTable
                caption={t('settings.scorecardRecentMisses')}
                frame="embedded"
                density="compact"
                columns={missColumns}
                rows={data.recentMisses}
                getRowKey={(miss, index) => `${miss.signalType}:${miss.horizon}:${miss.anchorDate ?? index}`}
                emptyState={{
                  title: t('settings.scorecardEmptyTitle'),
                  description: t('settings.scorecardEmptyDescription'),
                }}
              />
            ) : hasBuckets || hasDistribution ? (
              <p className="text-xs text-muted-text">{t('settings.scorecardNoMisses')}</p>
            ) : null}
          </>
        ) : null}
      </div>
    </SettingsSectionCard>
  );
};

export default SignalScorecardPanel;
