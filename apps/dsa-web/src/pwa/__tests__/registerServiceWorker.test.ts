// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it, vi } from 'vitest';
import {
  registerServiceWorker,
  shouldRegisterServiceWorker,
} from '../registerServiceWorker';

describe('registerServiceWorker', () => {
  it('skips registration when disabled or container is missing', () => {
    expect(shouldRegisterServiceWorker({ enabled: false, hasContainer: true })).toBe(false);
    expect(shouldRegisterServiceWorker({ enabled: true, hasContainer: false })).toBe(false);
    expect(shouldRegisterServiceWorker({ enabled: true, hasContainer: true })).toBe(true);
  });

  it('registers /sw.js at root scope when enabled', async () => {
    const register = vi.fn().mockResolvedValue({ scope: '/' });
    const result = await registerServiceWorker({
      enabled: true,
      container: { register },
    });
    expect(result).toEqual({ scope: '/' });
    expect(register).toHaveBeenCalledWith('/sw.js', {
      scope: '/',
      updateViaCache: 'none',
    });
  });

  it('swallows registration failures and reports them', async () => {
    const onError = vi.fn();
    const register = vi.fn().mockRejectedValue(new Error('blocked'));
    const result = await registerServiceWorker({
      enabled: true,
      container: { register },
      onError,
    });
    expect(result).toBeNull();
    expect(onError).toHaveBeenCalled();
  });
});
