// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import type { EventAlertDisplayItem } from '../../../types/eventAlerts';
import EventAlertList from '../EventAlertList';

function makeItem(index: number): EventAlertDisplayItem {
  return {
    id: index + 1,
    status: 'triggered',
    impactGrade: 'routine',
    impactProvenance: 'rule_severity',
    eventCategory: 'earnings',
    target: `SYM${String(index + 1).padStart(3, '0')}`,
    whyItMatters: `Wrapping impact copy for row ${index + 1} that exceeds one compact line.`,
    triggeredAt: '2026-08-10T08:00:00Z',
    degraded: false,
    inWatchlist: true,
    inPortfolio: false,
  };
}

describe('EventAlertList virtualization fallback', () => {
  it('keeps wrapping why-it-matters copy on the full DataTable path', () => {
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');
    render(
      <UiLanguageProvider initialLanguage="en">
        <EventAlertList items={Array.from({ length: 30 }, (_, index) => makeItem(index))} />
      </UiLanguageProvider>,
    );

    const table = screen.getByRole('table');
    const region = table.parentElement;
    expect(region).toHaveAttribute('data-data-table-virtualized', 'false');
    expect(region).toHaveAttribute('data-data-table-virtual-reason', 'disabled');
    expect(region).toHaveAttribute('data-mounted-count', '30');
    expect(within(table).getByText('SYM001')).toBeInTheDocument();
    expect(within(table).getByText('SYM030')).toBeInTheDocument();
    expect(within(table).getByText('Wrapping impact copy for row 30 that exceeds one compact line.')).toBeInTheDocument();
  });
});
