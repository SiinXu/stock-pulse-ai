// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { eventCalendarApi } from '../../../api/eventCalendar';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { APP_ROUTE_PATHS } from '../../../routing/routes';
import type { EventCalendarResponse } from '../../../types/eventCalendar';
import EventCalendarWorkspace from '../EventCalendarWorkspace';

vi.mock('../../../api/eventCalendar', () => ({
  eventCalendarApi: { getCalendar: vi.fn() },
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-path">{location.pathname}</div>;
}

function renderWorkspace(initialPath = APP_ROUTE_PATHS.eventCalendar) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <UiLanguageProvider initialLanguage="en">
        <Routes>
          <Route
            path={APP_ROUTE_PATHS.eventCalendar}
            element={(
              <>
                <EventCalendarWorkspace />
                <LocationProbe />
              </>
            )}
          />
          <Route
            path={APP_ROUTE_PATHS.eventAlerts}
            element={<LocationProbe />}
          />
        </Routes>
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

  it('exposes a production entry to event alerts without typed URLs', async () => {
    vi.mocked(eventCalendarApi.getCalendar).mockResolvedValue(emptyPayload);
    renderWorkspace();
    const openAlerts = await screen.findByTestId('event-calendar-open-alerts');
    expect(openAlerts).toHaveTextContent('Event-driven alerts');
    fireEvent.click(openAlerts);
    expect(await screen.findByTestId('location-path')).toHaveTextContent(APP_ROUTE_PATHS.eventAlerts);
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

  it('exposes a production entry to the corporate event alerts page (#1058)', async () => {
    vi.mocked(eventCalendarApi.getCalendar).mockResolvedValue(emptyPayload);
    renderWorkspace();
    const link = await screen.findByTestId('event-calendar-open-event-alerts');
    expect(link).toHaveAttribute('href', APP_ROUTE_PATHS.eventAlerts);
    expect(link).toHaveAccessibleName('Open event alerts');
  });
});
