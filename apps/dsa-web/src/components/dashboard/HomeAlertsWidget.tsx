// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { ArrowRight, BellRing } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button, EmptyState, Section, StatePanel } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import {
  SIGNAL_CENTER_HISTORY_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
  buildSignalCenterHref,
} from '../../routing/routes';

export type HomeAlertsWidgetProps = {
  isLoading: boolean;
  available: boolean;
  triggeredAlertTotal: number | null;
  onRetry: () => void;
};

export const HomeAlertsWidget: React.FC<HomeAlertsWidgetProps> = ({
  isLoading,
  available,
  triggeredAlertTotal,
  onRetry,
}) => {
  const { t } = useUiLanguage();
  const navigate = useNavigate();
  const total = triggeredAlertTotal ?? 0;
  const alertsHref = buildSignalCenterHref({
    tab: SIGNAL_CENTER_TAB_VALUES.history,
    history: SIGNAL_CENTER_HISTORY_VALUES.triggers,
  });

  return (
    <Section
      title={t('home.triggeredAlerts')}
      description={t('home.dashboardLayout.widget.alertsDescription')}
      level="interactive"
      padding="md"
      actions={<BellRing className="h-5 w-5 text-danger" aria-hidden="true" />}
      data-testid="home-alerts-widget"
    >
      {isLoading ? (
        <StatePanel state="loading" title={t('common.loading')} size="compact" titleAs="p" />
      ) : !available ? (
        <StatePanel
          state="error"
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
      ) : total > 0 ? (
        <button
          type="button"
          className="flex min-h-14 w-full items-center justify-between gap-3 rounded-lg border border-danger/25 bg-danger/10 px-3 py-2 text-left"
          onClick={() => navigate(alertsHref)}
        >
          <span>
            <span className="block text-sm font-semibold text-foreground">
              {t('home.dashboardLayout.widget.alertsCount', { count: total })}
            </span>
            <span className="mt-1 block text-xs text-secondary-text">
              {t('home.dashboardLayout.widget.alertsCountDescription')}
            </span>
          </span>
          <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
        </button>
      ) : (
        <EmptyState
          compact
          title={t('home.dashboardLayout.widget.alertsEmptyTitle')}
          description={t('home.dashboardLayout.widget.alertsEmptyDescription')}
          action={(
            <Button
              variant="secondary"
              size="default"
              onClick={() => navigate(alertsHref)}
            >
              {t('home.dashboardLayout.widget.openAlerts')}
            </Button>
          )}
        />
      )}
    </Section>
  );
};

export default HomeAlertsWidget;
