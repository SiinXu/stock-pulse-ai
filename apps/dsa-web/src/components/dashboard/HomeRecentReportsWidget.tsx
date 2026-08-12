// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { ArrowRight, History } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button, EmptyState, Section, StatePanel } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  buildAnalysisWorkbenchHref,
} from '../../routing/routes';
import type { HistoryItem } from '../../types/analysis';
import type { UiLanguage } from '../../i18n/uiText';
import { formatDateTime } from '../../utils/format';

export type HomeRecentReportsWidgetProps = {
  isLoading: boolean;
  available: boolean;
  items: HistoryItem[];
  language: UiLanguage;
  onRetry: () => void;
};

export const HomeRecentReportsWidget: React.FC<HomeRecentReportsWidgetProps> = ({
  isLoading,
  available,
  items,
  language,
  onRetry,
}) => {
  const { t } = useUiLanguage();
  const navigate = useNavigate();
  const analysisHref = buildAnalysisWorkbenchHref({
    segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
  });

  return (
    <Section
      title={t('home.recentAnalyses')}
      description={t('home.dashboardLayout.widget.recentReportsDescription')}
      level="interactive"
      padding="md"
      actions={<History className="h-5 w-5 text-primary" aria-hidden="true" />}
      data-testid="home-recent-reports-widget"
    >
      {isLoading ? (
        <StatePanel state="loading" title={t('common.loading')} size="compact" titleAs="p" />
      ) : items.length > 0 ? (
        <div className="divide-y divide-border/70">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              className="flex min-h-12 w-full items-center justify-between gap-3 py-2 text-left"
              onClick={() => navigate(buildAnalysisWorkbenchHref({ recordId: item.id }))}
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-foreground">
                  {item.stockName || item.stockCode}
                </span>
                <span className="mt-0.5 block truncate text-xs text-secondary-text">
                  {item.stockCode}
                  {' · '}
                  {formatDateTime(item.createdAt, language)}
                </span>
              </span>
              <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
            </button>
          ))}
        </div>
      ) : !available ? (
        <StatePanel
          state="partial"
          title={t('home.partialDataTitle')}
          description={t('home.partialDataMessage')}
          action={(
            <Button variant="secondary" size="default" onClick={onRetry}>
              {t('common.retry')}
            </Button>
          )}
          size="compact"
          titleAs="p"
        />
      ) : (
        <EmptyState
          compact
          title={t('home.noRecentAnalysesTitle')}
          description={t('home.noRecentAnalysesDescription')}
          action={(
            <Button variant="secondary" size="default" onClick={() => navigate(analysisHref)}>
              {t('home.startAnalysisTitle')}
            </Button>
          )}
        />
      )}
    </Section>
  );
};

export default HomeRecentReportsWidget;
