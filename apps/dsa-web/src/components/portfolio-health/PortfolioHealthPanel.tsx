// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { portfolioHealthApi } from '../../api/portfolioHealth';
import { formatParsedApiError, getParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PORTFOLIO_HEALTH_TEXT } from '../../locales/portfolioHealth';
import type {
  PortfolioHealthBand,
  PortfolioHealthDimensionKey,
  PortfolioHealthResponse,
  PortfolioHealthStatus,
} from '../../types/portfolioHealth';
import type { PortfolioCostMethod } from '../../types/portfolio';
import { formatUiNumber } from '../../utils/uiLocale';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  InlineAlert,
  Loading,
  StatePanel,
} from '../common';

type PortfolioHealthPanelProps = {
  accountId?: number;
  costMethod?: PortfolioCostMethod;
  asOf?: string;
};

const DIMENSION_KEYS: PortfolioHealthDimensionKey[] = [
  'concentration',
  'riskExposure',
  'diversification',
  'pnl',
  'cashRatio',
];

function statusVariant(status: PortfolioHealthStatus): 'success' | 'warning' | 'default' {
  if (status === 'ok') return 'success';
  if (status === 'partial') return 'warning';
  return 'default';
}

function healthQueryKey(query: { accountId?: number; costMethod: string; asOf?: string }): string {
  return `${query.accountId ?? ''}:${query.costMethod}:${query.asOf ?? ''}`;
}

const PortfolioHealthPanel: React.FC<PortfolioHealthPanelProps> = ({
  accountId,
  costMethod = 'fifo',
  asOf,
}) => {
  const { language } = useUiLanguage();
  const text = PORTFOLIO_HEALTH_TEXT[language];
  const requestIdRef = useRef(0);
  const refreshInFlightRef = useRef(false);
  const [data, setData] = useState<PortfolioHealthResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [refreshError, setRefreshError] = useState<ParsedApiError | null>(null);

  const query = useMemo(() => ({ accountId, costMethod, asOf }), [accountId, asOf, costMethod]);
  const queryKey = healthQueryKey(query);
  const [loadedQueryKey, setLoadedQueryKey] = useState<string | null>(null);
  const visibleData = loadedQueryKey === queryKey ? data : null;

  const load = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setLoadError(null);
    try {
      const response = await portfolioHealthApi.getSummary(query);
      if (requestIdRef.current !== requestId) return;
      setData(response);
      setLoadedQueryKey(healthQueryKey(query));
    } catch (error) {
      if (requestIdRef.current !== requestId) return;
      setData(null);
      setLoadedQueryKey(healthQueryKey(query));
      setLoadError(getParsedApiError(error, language));
    } finally {
      if (requestIdRef.current === requestId) setIsLoading(false);
    }
  }, [language, query]);

  useEffect(() => {
    void load();
    return () => {
      requestIdRef.current += 1;
    };
  }, [load]);

  const refresh = useCallback(async () => {
    if (refreshInFlightRef.current) return;
    refreshInFlightRef.current = true;
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsRefreshing(true);
    setRefreshError(null);
    try {
      const response = await portfolioHealthApi.refresh({ ...query, persist: true });
      if (requestIdRef.current === requestId) {
        setData(response);
        setLoadedQueryKey(healthQueryKey(query));
      }
    } catch (error) {
      if (requestIdRef.current === requestId) {
        setRefreshError(getParsedApiError(error, language));
      }
    } finally {
      refreshInFlightRef.current = false;
      if (requestIdRef.current === requestId) setIsRefreshing(false);
    }
  }, [language, query]);

  const isQueryCurrent = loadedQueryKey === queryKey;
  const showLoading = !isQueryCurrent || isLoading;
  const visibleLoadError = isQueryCurrent ? loadError : null;
  const statusLabel = visibleData
    ? {
        ok: text.statusOk,
        partial: text.statusPartial,
        empty_portfolio: text.statusEmpty,
        unavailable: text.statusUnavailable,
      }[visibleData.status]
    : null;
  const bandLabel = visibleData?.band
    ? ({
        healthy: text.bandHealthy,
        fair: text.bandFair,
        caution: text.bandCaution,
        poor: text.bandPoor,
      } satisfies Record<PortfolioHealthBand, string>)[visibleData.band]
    : null;
  const score = visibleData?.score ?? visibleData?.partialScore ?? null;
  const scoreLabel = visibleData?.score != null ? text.score : visibleData?.partialScore != null
    ? text.partialScore
    : text.noScore;

  return (
    <section
      className="space-y-3"
      aria-label={text.title}
      aria-busy={showLoading || isRefreshing || undefined}
      data-testid="portfolio-health-panel"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-foreground">{text.title}</h2>
          <p className="mt-1 text-xs text-secondary">{text.description}</p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="comfortable"
          onClick={() => void refresh()}
          disabled={showLoading || isRefreshing}
          isLoading={isRefreshing}
          loadingText={text.refreshing}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {text.refresh}
        </Button>
      </div>

      {refreshError ? (
        <InlineAlert
          variant="danger"
          size="compact"
          title={text.refreshFailedTitle}
          message={formatParsedApiError(refreshError) || refreshError.message}
          data-testid="portfolio-health-refresh-error"
        />
      ) : null}

      {showLoading ? <Loading label={text.loading} className="min-h-28" /> : null}

      {!showLoading && visibleLoadError ? (
        <StatePanel
          state="error"
          title={text.loadFailedTitle}
          description={formatParsedApiError(visibleLoadError) || visibleLoadError.message}
          action={(
            <Button type="button" variant="secondary" onClick={() => void load()}>
              {text.retry}
            </Button>
          )}
          size="compact"
          titleAs="h3"
        />
      ) : null}

      {!showLoading && !visibleLoadError && !visibleData ? (
        <EmptyState
          title={text.notGeneratedTitle}
          description={text.notGeneratedDescription}
          action={(
            <Button type="button" variant="primary" onClick={() => void refresh()}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              {text.refresh}
            </Button>
          )}
          data-testid="portfolio-health-empty"
        />
      ) : null}

      {visibleData?.status === 'empty_portfolio' ? (
        <EmptyState
          title={text.emptyTitle}
          description={visibleData.statusMessage || text.emptyDescription}
          compact
          data-testid="portfolio-health-empty-portfolio"
        />
      ) : null}

      {visibleData?.status === 'unavailable' ? (
        <StatePanel
          state="blocked"
          title={text.unavailableTitle}
          description={visibleData.statusMessage || text.unavailableDescription}
          size="compact"
          titleAs="h3"
          data-testid="portfolio-health-unavailable"
        />
      ) : null}

      {visibleData && visibleData.status !== 'empty_portfolio' && visibleData.status !== 'unavailable' ? (
        <>
          {visibleData.status === 'partial' ? (
            <InlineAlert
              variant="warning"
              size="compact"
              title={text.partialTitle}
              message={visibleData.statusMessage || text.partialDescription}
              data-testid="portfolio-health-partial"
            />
          ) : null}
          <Card padding="md">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs text-secondary">{scoreLabel}</p>
                <p className="mt-1 text-3xl font-semibold text-foreground" data-testid="portfolio-health-score">
                  {score == null ? '—' : formatUiNumber(score, language, { maximumFractionDigits: 1 })}
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                <Badge variant={statusVariant(visibleData.status)}>{text.status}: {statusLabel}</Badge>
                {bandLabel ? <Badge variant="info">{bandLabel}</Badge> : null}
              </div>
            </div>
            <dl className="mt-4 grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
              <div><dt className="text-secondary">{text.coverage}</dt><dd className="font-medium text-foreground">{formatUiNumber(visibleData.coverageRatio * 100, language, { maximumFractionDigits: 1 })}%</dd></div>
              <div><dt className="text-secondary">{text.asOf}</dt><dd className="font-medium text-foreground">{visibleData.asOf}</dd></div>
              <div><dt className="text-secondary">{text.persisted}</dt><dd className="font-medium text-foreground">{visibleData.persisted ? text.statusOk : '—'}</dd></div>
            </dl>
          </Card>

          <div>
            <h3 className="mb-2 text-sm font-semibold text-foreground">{text.dimensions}</h3>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-5">
              {DIMENSION_KEYS.map((key) => {
                const dimension = visibleData.dimensions[key];
                const label = {
                  concentration: text.dimensionConcentration,
                  riskExposure: text.dimensionRiskExposure,
                  diversification: text.dimensionDiversification,
                  pnl: text.dimensionPnl,
                  cashRatio: text.dimensionCashRatio,
                }[key];
                return (
                  <Card key={key} padding="sm">
                    <p className="text-xs text-secondary">{label}</p>
                    <p className="mt-1 text-lg font-semibold text-foreground">
                      {dimension.status === 'ok' && dimension.score != null
                        ? formatUiNumber(dimension.score, language, { maximumFractionDigits: 1 })
                        : '—'}
                    </p>
                    {dimension.status !== 'ok' ? (
                      <p className="mt-1 text-xs text-warning">
                        {dimension.statusMessage || dimension.reason || text.dimensionUnavailable}
                      </p>
                    ) : null}
                  </Card>
                );
              })}
            </div>
          </div>

          <Card padding="md">
            <h3 className="text-sm font-semibold text-foreground">{text.insights}</h3>
            {visibleData.insights.length ? (
              <ul className="mt-2 space-y-2 text-xs text-secondary">
                {visibleData.insights.map((insight, index) => (
                  <li key={`${insight.code}-${insight.symbol ?? 'portfolio'}-${index}`} className="flex items-start gap-2">
                    <Badge variant={insight.severity === 'warning' ? 'warning' : 'info'} size="sm">
                      {insight.severity}
                    </Badge>
                    <span>{insight.message}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="mt-2 text-xs text-secondary">{text.noInsights}</p>}
            <p className="mt-3 border-t border-subtle pt-3 text-xs text-muted-text">{visibleData.disclaimer}</p>
          </Card>
        </>
      ) : null}
    </section>
  );
};

export default PortfolioHealthPanel;
