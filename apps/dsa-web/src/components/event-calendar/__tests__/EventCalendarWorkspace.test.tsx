// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { eventCalendarApi } from '../../../api/eventCalendar';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { EventCalendarResponse } from '../../../types/eventCalendar';
import EventCalendarWorkspace from '../EventCalendarWorkspace';

vi.mock('../../../api/eventCalendar', () => ({
  eventCalendarApi: {
    getCalendar: vi.fn(),
  },
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

const disabledPayload: EventCalendarResponse = {
  enabled: false,
  fetchAttempted: false,
  asOf: '2026-08-09',
  dateFrom: '2026-08-09',
  dateTo: '2026-11-07',
  eventTypes: [],
  symbols: [],
  symbolCount: 0,
  eventCount: 0,
  events: [],
  coverage: [],
  sourcesAttempted: [],
  errors: [],
  coverageNotes: ['EVENT_CALENDAR_ENABLED is false; no provider fetch was attempted.'],
};

const emptyEnabledPayload: EventCalendarResponse = {
  ...disabledPayload,
  enabled: true,
  fetchAttempted: true,
  symbolCount: 2,
  coverageNotes: [],
  coverage: [
    {
      market: 'CN A-share',
      earnings: 'appointment',
      exDividend: 'announced',
      unlock: 'queue',
      indexRebalance: 'not covered (V0)',
      macro: 'not covered (V0)',
    },
  ],
};

const withEventsPayload: EventCalendarResponse = {
  ...emptyEnabledPayload,
  eventCount: 1,
  events: [
    {
      eventId: 'earnings:cn:600519:20260630:2026-08-20',
      eventType: 'earnings',
      eventDate: '2026-08-20',
      certainty: 'scheduled',
      symbol: '600519',
      title: '600519 earnings disclosure',
      impactPreview: {
        available: true,
        whyItMatters: 'Earnings events can reprice profit expectations and valuation anchors.',
        affected: { inWatchlist: true, inPortfolio: false },
      },
    },
  ],
};

describe('EventCalendarWorkspace', () => {
  beforeEach(() => {
    vi.mocked(eventCalendarApi.getCalendar).mockReset();
  });

  it('renders disabled empty state when calendar is off', async () => {
    vi.mocked(eventCalendarApi.getCalendar).mockResolvedValue(disabledPayload);
    renderWorkspace();
    await waitFor(() => {
      expect(screen.getByText('Event calendar is disabled')).toBeInTheDocument();
    });
    expect(screen.getByText(/EVENT_CALENDAR_ENABLED/i)).toBeInTheDocument();
  });

  it('renders empty state when enabled with no events', async () => {
    vi.mocked(eventCalendarApi.getCalendar).mockResolvedValue(emptyEnabledPayload);
    renderWorkspace();
    await waitFor(() => {
      expect(screen.getByText('No events in this range')).toBeInTheDocument();
    });
    expect(screen.getByText('Market coverage')).toBeInTheDocument();
  });

  it('renders certainty badge for scheduled events', async () => {
    vi.mocked(eventCalendarApi.getCalendar).mockResolvedValue(withEventsPayload);
    renderWorkspace();
    await waitFor(() => {
      expect(screen.getByText('600519')).toBeInTheDocument();
    });
    expect(screen.getByText('Scheduled (may change)')).toBeInTheDocument();
    expect(screen.getByText(/reprice profit expectations/i)).toBeInTheDocument();
  });
});
