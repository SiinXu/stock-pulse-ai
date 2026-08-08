// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { readParams, writeParams } from '../../../utils/urlState';
import { alertsUrlSchema } from '../alertsUrlState';

describe('alertsUrlSchema', () => {
  it('reads defaults for empty search', () => {
    expect(readParams(alertsUrlSchema, '')).toEqual({
      view: 'rules',
      enabled: 'all',
      type: 'all',
      page: 1,
      historyPage: 1,
      notificationsPage: 1,
      channel: 'all',
      success: 'all',
      alert: null,
      trigger: null,
    });
  });

  it('serializes filters with replace and selection with push', () => {
    const filters = writeParams(alertsUrlSchema, {
      enabled: 'disabled',
      type: 'price_cross',
      page: 2,
    }, { search: '' });
    expect(filters.history).toBe('replace');
    expect(filters.search).toContain('enabled=disabled');
    expect(filters.search).toContain('type=price_cross');
    expect(filters.search).toContain('page=2');

    const selection = writeParams(alertsUrlSchema, { alert: 9 }, { search: filters.search });
    expect(selection.history).toBe('push');
    expect(selection.search).toContain('alert=9');
    expect(selection.search).toContain('enabled=disabled');
  });

  it('omits default values and preserves unknown keys', () => {
    const result = writeParams(alertsUrlSchema, { enabled: 'all', page: 1 }, {
      search: '?keep=yes&enabled=disabled',
    });
    expect(result.search).toBe('?keep=yes');
  });
});
