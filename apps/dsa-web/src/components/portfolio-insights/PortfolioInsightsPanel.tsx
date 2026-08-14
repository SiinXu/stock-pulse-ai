// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { lazy, Suspense } from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PORTFOLIO_INSIGHTS_TEXT } from '../../locales/portfolioInsights';
import type { PortfolioCostMethod } from '../../types/portfolio';
import type { PortfolioInsightsView } from '../portfolio/portfolioUrlState';
import { Loading, SegmentedControl } from '../common';
import { getTabPanelId } from '../common/tabIds';

const PortfolioHealthPanel = lazy(() => import('../portfolio-health/PortfolioHealthPanel'));
const BasketAnalysisView = lazy(() => import('./BasketAnalysisView'));
const StressTestView = lazy(() => import('./StressTestView'));
const RebalanceView = lazy(() => import('./RebalanceView'));

type Props = {
  view: PortfolioInsightsView;
  onViewChange: (view: PortfolioInsightsView) => void;
  accountId?: number;
  costMethod: PortfolioCostMethod;
};

const TABS_ID = 'portfolio-insights-views';

const PortfolioInsightsPanel: React.FC<Props> = ({ view, onViewChange, accountId, costMethod }) => {
  const { language } = useUiLanguage();
  const text = PORTFOLIO_INSIGHTS_TEXT[language];
  return (
    <section className="space-y-4" data-testid="portfolio-insights-panel">
      <SegmentedControl
        id={TABS_ID}
        value={view}
        onChange={onViewChange}
        ariaLabel={text.viewsLabel}
        getPanelId={(value) => getTabPanelId(TABS_ID, value)}
        options={[
          { value: 'health', label: text.healthView },
          { value: 'basket', label: text.basketView },
          { value: 'stress', label: text.stressView },
          { value: 'rebalance', label: text.rebalanceView },
        ]}
      />
      <div id={getTabPanelId(TABS_ID, view)} role="tabpanel" aria-labelledby={`${TABS_ID}--tab--${view}`}>
        <Suspense fallback={<Loading />}>
          {view === 'health' ? <PortfolioHealthPanel accountId={accountId} costMethod={costMethod} /> : null}
          {view === 'basket' ? <BasketAnalysisView /> : null}
          {view === 'stress' ? <StressTestView accountId={accountId} costMethod={costMethod} /> : null}
          {view === 'rebalance' ? <RebalanceView accountId={accountId} costMethod={costMethod} /> : null}
        </Suspense>
      </div>
    </section>
  );
};

export default PortfolioInsightsPanel;
