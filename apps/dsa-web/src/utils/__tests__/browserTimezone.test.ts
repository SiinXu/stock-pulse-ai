// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getBrowserTimezone } from '../browserTimezone';

describe('getBrowserTimezone', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns the resolved Intl timezone when present', () => {
    vi.spyOn(Intl.DateTimeFormat.prototype, 'resolvedOptions').mockReturnValue({
      locale: 'en-US',
      calendar: 'gregory',
      numberingSystem: 'latn',
      timeZone: 'America/New_York',
    });
    expect(getBrowserTimezone()).toBe('America/New_York');
  });

  it('falls back to UTC when Intl returns an empty timezone', () => {
    vi.spyOn(Intl.DateTimeFormat.prototype, 'resolvedOptions').mockReturnValue({
      locale: 'en-US',
      calendar: 'gregory',
      numberingSystem: 'latn',
      timeZone: '',
    });
    expect(getBrowserTimezone()).toBe('UTC');
  });

  it('falls back to UTC when Intl timezone lookup throws', () => {
    vi.spyOn(Intl.DateTimeFormat.prototype, 'resolvedOptions').mockImplementation(() => {
      throw new Error('timezone unavailable');
    });
    expect(getBrowserTimezone()).toBe('UTC');
  });
});
