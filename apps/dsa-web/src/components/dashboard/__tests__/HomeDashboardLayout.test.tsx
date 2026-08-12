// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { resetDashboardLayoutStoreForTests } from '../../../stores/dashboardLayoutStore';
import { HomeDashboardLayout } from '../HomeDashboardLayout';

function renderLayout() {
  return render(
    <MemoryRouter>
      <UiLanguageProvider>
        <HomeDashboardLayout
          widgets={{
            watchlist: <div>Watchlist body</div>,
            portfolio_health: <div>Health body</div>,
            alerts: <div>Alerts body</div>,
            recent_reports: <div>Reports body</div>,
          }}
        />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
}

describe('HomeDashboardLayout', () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetDashboardLayoutStoreForTests();
  });

  it('renders the four widgets and supports keyboard reorder in customize mode', () => {
    renderLayout();
    expect(screen.getByTestId('home-dashboard-layout')).toBeInTheDocument();
    expect(screen.getByTestId('home-dashboard-widget-watchlist')).toBeInTheDocument();
    expect(screen.getByText('Watchlist body')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('home-dashboard-layout-customize'));
    const handle = screen.getByTestId('home-dashboard-drag-watchlist');
    expect(handle).toHaveAttribute('draggable', 'true');
    fireEvent.keyDown(handle, { key: 'ArrowDown' });
    expect(screen.getByTestId('home-dashboard-layout-announcement')).not.toBeEmptyDOMElement();

    const board = screen.getByTestId('home-dashboard-layout-board');
    const widgets = board.querySelectorAll('[data-testid^="home-dashboard-widget-"]');
    expect(widgets[0]?.getAttribute('data-testid')).toBe('home-dashboard-widget-portfolio_health');
  });

  it('exposes mobile non-drag move controls and blocks hiding the last widget', () => {
    renderLayout();
    fireEvent.click(screen.getByTestId('home-dashboard-layout-customize'));
    expect(screen.getByTestId('home-dashboard-move-up-watchlist')).toBeInTheDocument();
    expect(screen.getByTestId('home-dashboard-move-down-watchlist')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('home-dashboard-toggle-portfolio_health'));
    fireEvent.click(screen.getByTestId('home-dashboard-toggle-alerts'));
    fireEvent.click(screen.getByTestId('home-dashboard-toggle-recent_reports'));
    const lastToggle = screen.getByTestId('home-dashboard-toggle-watchlist');
    expect(lastToggle).toBeDisabled();
  });
});
