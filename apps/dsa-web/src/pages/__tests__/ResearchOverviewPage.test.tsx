// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  APPLICATION_NAVIGATION_ITEMS,
  type ApplicationNavigationGroup,
} from '../../components/layout/navigation';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import {
  RouteFocusRegistrationContext,
  type RouteFocusTarget,
} from '../../contexts/routeFocusContext';
import { FINANCIAL_CALCULATORS_TEXT } from '../../locales/financialCalculators';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import { recordSessionLocation } from '../../utils/sessionContinuity';
import ResearchOverviewPage from '../ResearchOverviewPage';

const routeFocusRegister = vi.fn((target: RouteFocusTarget) => {
  void target;
  return () => {};
});

function renderPage() {
  return render(
    <RouteFocusRegistrationContext.Provider value={{ register: routeFocusRegister }}>
      <UiLanguageProvider initialLanguage="zh">
        <MemoryRouter initialEntries={[APP_ROUTE_PATHS.research]}>
          <ResearchOverviewPage />
        </MemoryRouter>
      </UiLanguageProvider>
    </RouteFocusRegistrationContext.Provider>,
  );
}

describe('ResearchOverviewPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    document.title = '';
  });

  it('presents the Research tools as an independent, focusable route', () => {
    recordSessionLocation(
      `${APP_ROUTE_PATHS.researchDiscover}?strategy=quality&count=20`,
    );

    renderPage();

    expect(screen.getByTestId('research-overview-page')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: '研究' })).toBeInTheDocument();
    for (const title of ['大盘复盘', '发现', '分析工作台', '回测', '事件日历', '金融计算器', '技能后验']) {
      expect(screen.getByRole('heading', { level: 2, name: title })).toBeInTheDocument();
    }

    expect(screen.getByRole('link', { name: '进入大盘复盘' }))
      .toHaveAttribute('href', APP_ROUTE_PATHS.researchMarket);
    expect(screen.getByRole('link', { name: '进入发现' }))
      .toHaveAttribute(
        'href',
        `${APP_ROUTE_PATHS.researchDiscover}?strategy=quality&count=20`,
      );
    expect(screen.getByRole('link', { name: '进入分析工作台' }))
      .toHaveAttribute('href', APP_ROUTE_PATHS.researchAnalysis);
    expect(screen.getByRole('link', { name: '进入回测' }))
      .toHaveAttribute('href', APP_ROUTE_PATHS.researchBacktest);
    expect(screen.getByRole('link', { name: '进入事件日历' }))
      .toHaveAttribute('href', APP_ROUTE_PATHS.eventCalendar);
    expect(screen.getByRole('link', { name: '进入金融计算器' }))
      .toHaveAttribute('href', APP_ROUTE_PATHS.calculators);
    expect(screen.getByRole('link', { name: '进入技能后验' }))
      .toHaveAttribute('href', APP_ROUTE_PATHS.researchSkillOutcomes);
    expect(screen.getByText(FINANCIAL_CALCULATORS_TEXT.zh.description)).toBeInTheDocument();
    expect(document.title).toBe('研究 - StockPulse');
    expect(routeFocusRegister).toHaveBeenCalledWith(expect.objectContaining({
      routeId: APP_ROUTE_PATHS.research,
      ready: true,
    }));
  });

  it('lists every intended Research sidebar child, including calculators', () => {
    renderPage();

    const researchGroup = APPLICATION_NAVIGATION_ITEMS.find(
      (item): item is ApplicationNavigationGroup => item.kind === 'group' && item.key === 'research',
    );
    expect(researchGroup).toBeDefined();

    const intendedHrefs = researchGroup!.children.map((child) => child.to);
    const overviewHrefs = screen
      .getAllByRole('link')
      .filter((link) => link.getAttribute('data-control') === 'navigation-link')
      .map((link) => link.getAttribute('href'));

    expect(overviewHrefs).toEqual(intendedHrefs);
    expect(overviewHrefs).toContain(APP_ROUTE_PATHS.calculators);
  });
});
