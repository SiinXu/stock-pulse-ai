// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { eventCalendarApi } from '../eventCalendar';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('../index', () => ({ default: { get } }));

const trigger = (id: number, date: string) => ({
  id,
  target: '600519',
  status: 'triggered',
  triggered_at: `${date}T08:00:00Z`,
  data_source: 'corporate_event_service',
  impact_context: {
    event_category: 'earnings',
    what_happened: `Event ${id}`,
    why_it_matters: `Impact ${id}`,
    affected: { in_watchlist: true, in_portfolio: false },
  },
});

describe('eventCalendarApi', () => {
  beforeEach(() => get.mockReset());

  it('reads every server page before applying the date range', async () => {
    get
      .mockResolvedValueOnce({ data: { items: [trigger(1, '2026-07-01')], total: 2, page: 1, page_size: 100 } })
      .mockResolvedValueOnce({ data: { items: [trigger(2, '2026-08-10')], total: 2, page: 2, page_size: 100 } });

    const result = await eventCalendarApi.getCalendar({ dateFrom: '2026-08-01', dateTo: '2026-08-31' });

    expect(get).toHaveBeenCalledTimes(2);
    expect(get.mock.calls[0][1].params.alert_type).toBe('corporate_event');
    expect(get.mock.calls[1][1].params.page).toBe(2);
    expect(result.events.map((item) => item.eventId)).toEqual([2]);
    expect(result.loadedCount).toBe(2);
  });

  it('returns structured partial provenance when a later page fails', async () => {
    get
      .mockResolvedValueOnce({ data: { items: [trigger(1, '2026-08-10')], total: 2, page: 1, page_size: 100 } })
      .mockRejectedValueOnce(new Error('later page unavailable'));

    const result = await eventCalendarApi.getCalendar({ dateFrom: '2026-08-01', dateTo: '2026-08-31' });

    expect(result.events).toHaveLength(1);
    expect(result.partialErrors).toEqual(['event_calendar_page_unavailable']);
  });

  it('fails the request when the event source is wholly unavailable', async () => {
    get.mockRejectedValueOnce(new Error('source unavailable'));
    await expect(eventCalendarApi.getCalendar({ dateFrom: '2026-08-01', dateTo: '2026-08-31' }))
      .rejects.toThrow('source unavailable');
  });

  it('passes cancellation to the alerts request', async () => {
    const controller = new AbortController();
    get.mockResolvedValueOnce({ data: { items: [], total: 0, page: 1, page_size: 100 } });
    await eventCalendarApi.getCalendar(
      { dateFrom: '2026-08-01', dateTo: '2026-08-31' },
      { signal: controller.signal },
    );
    expect(get.mock.calls[0][1].signal).toBe(controller.signal);
  });
});
