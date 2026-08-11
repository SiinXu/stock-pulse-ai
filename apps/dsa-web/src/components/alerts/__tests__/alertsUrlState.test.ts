// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { readParams, writeParams } from '../../../utils/urlState';
import { SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS } from '../../../routing/routes';
import { alertsUrlSchema } from '../alertsUrlState';

describe('alertsUrlSchema', () => {
  it('reads defaults for empty search', () => {
    expect(readParams(alertsUrlSchema, '')).toEqual({
      enabled: 'all',
      type: 'all',
      page: 1,
      historyPage: 1,
      notificationsPage: 1,
      channel: 'all',
      success: 'all',
      alert: null,
    });
  });

  it('serializes filters with replace and selection with push', () => {
    const filters = writeParams(alertsUrlSchema, {
      enabled: 'disabled',
      type: 'price_cross',
      page: 2,
    }, { search: '' });
    expect(filters.history).toBe('replace');
    expect(filters.params.get(SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.rulesEnabled)).toBe('disabled');
    expect(filters.params.get(SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.rulesType)).toBe('price_cross');
    expect(filters.params.get(SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.rulesPage)).toBe('2');

    const selection = writeParams(alertsUrlSchema, { alert: 9 }, { search: filters.search });
    expect(selection.history).toBe('push');
    expect(selection.params.get(SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.alert)).toBe('9');
    expect(selection.params.get(SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.rulesEnabled)).toBe('disabled');
  });

  it('omits default values and preserves unknown keys', () => {
    const result = writeParams(alertsUrlSchema, { enabled: 'all', page: 1 }, {
      search: `?keep=yes&${SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.rulesEnabled}=disabled`,
    });
    expect(result.search).toBe('?keep=yes');
  });
});
