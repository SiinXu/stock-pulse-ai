// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { portfolioHealthApi } from '../../api/portfolioHealth';
import { parseApiError, type ParsedApiError } from '../../api/error';
import { Button, EmptyState, Section, StatePanel } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import type { PortfolioHealthSummary } from '../../types/portfolioHealth';

export type HomePortfolioHealthWidgetProps = {
  refreshKey?: string | number;
};

export const HomePortfolioHealthWidget: React.FC<HomePortfolioHealthWidgetProps> = ({
  refreshKey = 0,
}) => {
  const { t } = useUiLanguage();
  const navigate = useNavigate();
  const requestIdRef = useRef(0);
  const [data, setData] = useState<PortfolioHealthSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const load = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setError(null);
    try {
      const summary = await portfolioHealthApi.getSummary();
      if (requestIdRef.current !== requestId) return;
      setData(summary);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      setData(null);
      setError(parseApiError(err));
    } finally {
      if (requestIdRef.current === requestId) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      requestIdRef.current += 1;
    };
  }, [load, refreshKey]);

  const openPortfolio = () => navigate(APP_ROUTE_PATHS.portfolio);

  return (
    <Section
      title={t('home.dashboardLayout.widget.portfolioHealth')}
      description={t('home.dashboardLayout.widget.portfolioHealthDescription')}
      level="interactive"
      padding="md"
      actions={<Activity className="h-5 w-5 text-primary" aria-hidden="true" />}
      data-testid="home-portfolio-health-widget"
    >
      {isLoading ? (
        <StatePanel state="loading" title={t('common.loading')} size="compact" titleAs="p" />
      ) : error ? (
        <StatePanel
          state="error"
          title={t('home.dashboardLayout.widget.portfolioHealthUnavailable')}
          description={error.message || t('home.partialDataMessage')}
          action={(
            <Button variant="secondary" size="default" onClick={() => { void load(); }}>
              {t('common.retry')}
            </Button>
          )}
          size="compact"
          titleAs="p"
        />
      ) : !data || data.status === 'empty_portfolio' || data.status === 'unavailable' ? (
        <EmptyState
          compact
          title={t('home.dashboardLayout.widget.portfolioHealthEmptyTitle')}
          description={t('home.dashboardLayout.widget.portfolioHealthEmptyDescription')}
          action={(
            <Button variant="secondary" size="default" onClick={openPortfolio}>
              {t('home.dashboardLayout.widget.openPortfolio')}
            </Button>
          )}
        />
      ) : (
        <button
          type="button"
          className="flex min-h-14 w-full items-center justify-between gap-3 text-left"
          onClick={openPortfolio}
        >
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-foreground">
              {data.score != null && Number.isFinite(data.score)
                ? t('home.dashboardLayout.widget.portfolioHealthScore', {
                  score: Math.round(data.score),
                })
                : data.partialScore != null && Number.isFinite(data.partialScore)
                  ? t('home.dashboardLayout.widget.portfolioHealthPartialScore', {
                    score: Math.round(data.partialScore),
                  })
                  : t('home.dashboardLayout.widget.portfolioHealthNoScore')}
            </span>
            <span className="mt-1 block text-xs text-secondary-text">
              {data.band
                ? t(`home.dashboardLayout.widget.portfolioHealthBand.${data.band}`)
                : t('home.dashboardLayout.widget.portfolioHealthStatus', {
                  status: data.status,
                })}
              {' · '}
              {data.asOf}
            </span>
          </span>
          <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
        </button>
      )}
    </Section>
  );
};

export default HomePortfolioHealthWidget;
