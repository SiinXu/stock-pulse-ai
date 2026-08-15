// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { lazy, Suspense } from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { PortfolioCostMethod } from '../../types/portfolio';
import { getTabId, getTabPanelId, Loading, SegmentedControl } from '../common';
import type { PortfolioInsightView } from '../portfolio/portfolioUrlState';
import { usePortfolioInsightsText } from './usePortfolioInsightsText';

const PortfolioHealthPanel = lazy(() => import('./PortfolioHealthPanel'));
const PortfolioBasketPanel = lazy(() => import('./PortfolioBasketPanel'));
const PortfolioStressPanel = lazy(() => import('./PortfolioStressPanel'));
const PortfolioRebalancePanel = lazy(() => import('./PortfolioRebalancePanel'));

type PortfolioInsightsWorkspaceProps = {
  activeView: PortfolioInsightView;
  onViewChange: (view: PortfolioInsightView) => void;
  accountId?: number;
  costMethod: PortfolioCostMethod;
};

const PortfolioInsightsWorkspace: React.FC<PortfolioInsightsWorkspaceProps> = ({
  activeView,
  onViewChange,
  accountId,
  costMethod,
}) => {
  const { language } = useUiLanguage();
  const text = usePortfolioInsightsText(language);
  return (
    <section className="space-y-4" data-testid="portfolio-insights-workspace">
      <SegmentedControl
        id="portfolio-insights-views"
        ariaLabel={text.workspaceLabel}
        value={activeView}
        onChange={onViewChange}
        getPanelId={(view) => getTabPanelId('portfolio-insights-views', view)}
        options={[
          { value: 'health', label: text.health },
          { value: 'basket', label: text.basket },
          { value: 'stress', label: text.stress },
          { value: 'rebalance', label: text.rebalance },
        ]}
      />
      <div
        id={getTabPanelId('portfolio-insights-views', activeView)}
        role="tabpanel"
        aria-labelledby={getTabId('portfolio-insights-views', activeView)}
      >
        <Suspense fallback={<Loading />}>
          {activeView === 'health' ? (
            <PortfolioHealthPanel accountId={accountId} costMethod={costMethod} text={text} />
          ) : null}
          {activeView === 'basket' ? <PortfolioBasketPanel text={text} /> : null}
          {activeView === 'stress' ? (
            <PortfolioStressPanel accountId={accountId} costMethod={costMethod} text={text} />
          ) : null}
          {activeView === 'rebalance' ? (
            <PortfolioRebalancePanel accountId={accountId} costMethod={costMethod} text={text} />
          ) : null}
        </Suspense>
      </div>
    </section>
  );
};

export default PortfolioInsightsWorkspace;
