// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import {
  RouteFocusRegistrationContext,
  type RouteFocusTarget,
} from '../../contexts/routeFocusContext';
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

  it('presents the four Research tools as an independent, focusable route', () => {
    recordSessionLocation(
      `${APP_ROUTE_PATHS.researchDiscover}?strategy=quality&count=20`,
    );

    renderPage();

    expect(screen.getByTestId('research-overview-page')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: '研究' })).toBeInTheDocument();
    for (const title of ['大盘复盘', '发现', '分析工作台', '回测']) {
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
    expect(document.title).toBe('研究 - StockPulse');
    expect(routeFocusRegister).toHaveBeenCalledWith(expect.objectContaining({
      routeId: APP_ROUTE_PATHS.research,
      ready: true,
    }));
  });
});
