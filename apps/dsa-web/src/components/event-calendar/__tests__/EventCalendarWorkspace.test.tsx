// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { eventCalendarApi } from '../../../api/eventCalendar';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { EventCalendarResponse } from '../../../types/eventCalendar';
import EventCalendarWorkspace from '../EventCalendarWorkspace';

vi.mock('../../../api/eventCalendar', () => ({
  eventCalendarApi: { getCalendar: vi.fn() },
}));

function renderWorkspace() {
  return render(
    <MemoryRouter>
      <UiLanguageProvider initialLanguage="en">
        <EventCalendarWorkspace />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
}

const emptyPayload: EventCalendarResponse = {
  events: [],
  loadedCount: 0,
  total: 0,
  partialErrors: [],
};

const eventPayload = (summary: string): EventCalendarResponse => ({
  events: [{
    eventId: 7,
    eventDate: '2026-08-10',
    symbol: '600519',
    status: 'triggered',
    eventCategory: 'earnings',
    whatHappened: 'Earnings disclosure',
    whyItMatters: summary,
    degraded: false,
    inWatchlist: true,
    inPortfolio: false,
    source: 'corporate_event_service',
  }],
  loadedCount: 1,
  total: 1,
  partialErrors: [],
});

describe('EventCalendarWorkspace', () => {
  beforeEach(() => {
    vi.mocked(eventCalendarApi.getCalendar).mockReset();
  });

  it('renders an honest empty state after a complete read', async () => {
    vi.mocked(eventCalendarApi.getCalendar).mockResolvedValue(emptyPayload);
    renderWorkspace();
    expect(await screen.findByText('No corporate events in this date range')).toBeInTheDocument();
  });

  it('renders the alert contract impact projection in the shared DataTable', async () => {
    vi.mocked(eventCalendarApi.getCalendar).mockResolvedValue(eventPayload('Profit expectations may reprice.'));
    renderWorkspace();
    expect(await screen.findByText('600519')).toBeInTheDocument();
    expect(screen.getByText('Earnings')).toBeInTheDocument();
    expect(screen.getByText('Profit expectations may reprice.')).toBeInTheDocument();
    expect(screen.getByText('Watchlist')).toBeInTheDocument();
  });

  it('does not claim an incomplete result is empty', async () => {
    vi.mocked(eventCalendarApi.getCalendar).mockResolvedValue({
      ...emptyPayload,
      total: 25,
      partialErrors: ['event_calendar_page_unavailable'],
    });
    renderWorkspace();
    expect(await screen.findByText('This date range cannot be confirmed empty')).toBeInTheDocument();
    expect(screen.queryByText('No corporate events in this date range')).not.toBeInTheDocument();
  });

  it('aborts the previous generation and ignores its late response', async () => {
    let resolveFirst: (value: EventCalendarResponse) => void = () => undefined;
    const first = new Promise<EventCalendarResponse>((resolve) => { resolveFirst = resolve; });
    vi.mocked(eventCalendarApi.getCalendar)
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce(eventPayload('Newest response'));

    renderWorkspace();
    await waitFor(() => expect(eventCalendarApi.getCalendar).toHaveBeenCalledTimes(1));
    const firstSignal = vi.mocked(eventCalendarApi.getCalendar).mock.calls[0][1]?.signal;
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));

    expect(await screen.findByText('Newest response')).toBeInTheDocument();
    expect(firstSignal?.aborted).toBe(true);
    await act(async () => { resolveFirst(eventPayload('Stale response')); });
    expect(screen.queryByText('Stale response')).not.toBeInTheDocument();
    expect(screen.getByText('Newest response')).toBeInTheDocument();
  });
});
