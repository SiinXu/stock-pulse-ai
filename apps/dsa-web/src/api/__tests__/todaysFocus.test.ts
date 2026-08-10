import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getParsedApiError } from '../error';
import { getTodaysFocus } from '../todaysFocus';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('../index', () => ({ default: { get } }));

function validPayload() {
  return {
    pack_version: 'todays_focus/2.0',
    generated_at: '2026-08-09T08:00:00Z',
    status: 'ok',
    max_items: 5,
    item_count: 1,
    items: [{
      code: 'AAPL',
      name: 'Apple',
      reason_code: 'analysis_reversal',
      reason_display: 'Analysis conclusion changed: buy to sell',
      priority: 70,
      weight_pct: null,
      secondary_reason_codes: [],
      evidence: {
        type: 'analysis',
        record_id: 42,
        query_id: 'q-42',
        observed_at: '2026-08-09T07:00:00Z',
        previous_observed_at: '2026-08-08T07:00:00Z',
        previous_action: 'buy',
        latest_action: 'sell',
      },
    }],
    empty_reason: null,
    empty_message: null,
    sources_used: ['analysis_history'],
    degraded_sources: [],
    temporal_policy: {
      semantics: 'local_calendar_day',
      timezone: 'Asia/Shanghai',
      local_date: '2026-08-09',
      window_start: '2026-08-08T16:00:00Z',
      window_end: '2026-08-09T08:00:00Z',
      naive_timestamp_policy: 'assume_utc',
      missing_timestamp_policy: 'exclude',
      non_trading_day_policy: 'same_local_day_only',
    },
    universe_contract: {
      symbol_count: 1,
      hard_cap: 1000,
      truncated: false,
      sources: ['watchlist_config'],
    },
    cost_contract: {
      alert_repository_calls: 1,
      portfolio_repository_calls: 1,
      analysis_history_repository_calls: 1,
      event_repository_calls: 0,
      database_writes: 0,
      provider_calls: 0,
      analysis_runs_triggered: 0,
      zero_extra_fetch: true,
      read_only: true,
    },
    presentation_boundary: {
      alerts_owned_by: 'signal_center',
      focus_shows: 'prioritized_symbols_with_evidence_links',
      duplicate_alert_ui: false,
    },
  };
}

describe('getTodaysFocus', () => {
  beforeEach(() => get.mockReset());

  it('validates and camel-cases typed evidence', async () => {
    get.mockResolvedValueOnce({ data: validPayload() });
    const result = await getTodaysFocus({ maxItems: 5, accountId: 2, language: 'en' });
    expect(get).toHaveBeenCalledWith('/focus/today', {
      params: { max_items: 5, account_id: 2, language: 'en' },
    });
    expect(result.items[0].evidence).toMatchObject({
      type: 'analysis',
      recordId: 42,
      latestAction: 'sell',
    });
  });

  it.each([Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    'rejects a non-finite weight (%s)',
    async (invalid) => {
      const payload = validPayload();
      (payload.items[0] as { weight_pct: number | null }).weight_pct = invalid;
      get.mockResolvedValueOnce({ data: payload });
      await expect(getTodaysFocus()).rejects.toSatisfy((error: unknown) => {
        expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
        return true;
      });
    },
  );

  it('rejects unknown or mismatched evidence before rendering', async () => {
    const payload = validPayload();
    payload.items[0].evidence = { type: 'unknown' } as never;
    get.mockResolvedValueOnce({ data: payload });
    await expect(getTodaysFocus()).rejects.toSatisfy((error: unknown) => {
      expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
      return true;
    });
  });
});
