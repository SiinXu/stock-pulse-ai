// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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
    const dashboard = screen.getByRole('region', { name: 'Dashboard layout' });
    expect(within(dashboard).getByText('Watchlist body')).toBeInTheDocument();

    fireEvent.click(within(dashboard).getByRole('button', { name: 'Customize layout' }));
    const handle = within(dashboard).getByRole('button', {
      name: 'Reorder Watchlist; use Arrow Up or Arrow Down',
    });
    expect(handle).toHaveAttribute('draggable', 'true');
    fireEvent.keyDown(handle, { key: 'ArrowDown' });
    expect(within(dashboard).getByRole('status')).toHaveTextContent('Dashboard widgets reordered');

    const widgets = within(within(dashboard).getByRole('list')).getAllByRole('listitem');
    expect(within(widgets[0]!).getByText('Health body')).toBeInTheDocument();
  });

  it('exposes mobile non-drag move controls and blocks hiding the last widget', () => {
    renderLayout();
    const dashboard = screen.getByRole('region', { name: 'Dashboard layout' });
    fireEvent.click(within(dashboard).getByRole('button', { name: 'Customize layout' }));
    expect(within(dashboard).getByRole('button', { name: 'Move Watchlist up' })).toBeInTheDocument();
    expect(within(dashboard).getByRole('button', { name: 'Move Watchlist down' })).toBeInTheDocument();
    expect(within(dashboard).getByText(/On touch devices/)).toBeInTheDocument();

    fireEvent.click(within(dashboard).getByRole('button', { name: 'Hide Portfolio health' }));
    fireEvent.click(within(dashboard).getByRole('button', { name: 'Hide Triggered alerts' }));
    fireEvent.click(within(dashboard).getByRole('button', { name: 'Hide Recent analyses' }));
    const lastToggle = within(dashboard).getByRole('button', { name: 'Hide Watchlist' });
    expect(lastToggle).toBeDisabled();
  });

  it('restores defaults from customize mode', () => {
    renderLayout();
    const dashboard = screen.getByRole('region', { name: 'Dashboard layout' });
    fireEvent.click(within(dashboard).getByRole('button', { name: 'Customize layout' }));
    fireEvent.click(within(dashboard).getByRole('button', { name: 'Hide Triggered alerts' }));
    fireEvent.click(within(dashboard).getByRole('button', { name: 'Reset to default' }));
    fireEvent.click(within(dashboard).getByRole('button', { name: 'Done customizing' }));
    expect(within(dashboard).getByText('Alerts body')).toBeInTheDocument();
    expect(within(dashboard).getByRole('status')).toHaveTextContent(/default/i);
  });

  it('surfaces storage write failures in status text and the live announcement', () => {
    const setItem = vi.spyOn(
      Object.getPrototypeOf(window.localStorage) as Storage,
      'setItem',
    ).mockImplementation(() => {
      throw new DOMException('The quota has been exceeded.', 'QuotaExceededError');
    });
    try {
      renderLayout();
      const dashboard = screen.getByRole('region', { name: 'Dashboard layout' });
      fireEvent.click(within(dashboard).getByRole('button', { name: 'Customize layout' }));
      fireEvent.click(within(dashboard).getByRole('button', { name: 'Hide Triggered alerts' }));
      expect(within(dashboard).getByTestId('home-dashboard-layout-error')).toHaveTextContent(
        'Could not save the layout in this browser. The change was not applied.',
      );
      expect(within(dashboard).getByTestId('home-dashboard-layout-announcement')).toHaveTextContent(
        'Could not save the layout in this browser. The change was not applied.',
      );
    } finally {
      setItem.mockRestore();
    }
  });
});
