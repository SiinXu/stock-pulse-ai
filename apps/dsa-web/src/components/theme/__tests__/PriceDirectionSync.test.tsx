// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { act, render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { THEME_STORAGE_KEYS } from '../../../design/theme';
import { createDeferred } from '../../../test-utils';
import { PriceDirectionSync } from '../PriceDirectionSync';
import { ThemeAppearanceProvider } from '../ThemeAppearanceProvider';
import { applyPriceDirection } from '../themeRuntime';

const { getConfig } = vi.hoisted(() => ({
  getConfig: vi.fn(),
}));

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    getConfig,
  },
}));

describe('PriceDirectionSync', () => {
  beforeEach(() => {
    document.documentElement.removeAttribute('data-price-direction');
    localStorage.removeItem(THEME_STORAGE_KEYS.priceDirection);
    getConfig.mockReset();
  });

  it('applies and persists the server color scheme when no draft preview is active', async () => {
    applyPriceDirection('cn');
    getConfig.mockResolvedValue({
      items: [{ key: 'MARKET_REVIEW_COLOR_SCHEME', value: 'green_up' }],
    });

    render(
      <ThemeAppearanceProvider>
        <PriceDirectionSync />
      </ThemeAppearanceProvider>,
    );

    await waitFor(() => {
      expect(document.documentElement).toHaveAttribute('data-price-direction', 'us');
    });
    expect(localStorage.getItem(THEME_STORAGE_KEYS.priceDirection)).toBe('us');
  });

  it('does not revert or persist over a session-only Settings draft preview', async () => {
    applyPriceDirection('cn');
    const pending = createDeferred<{ items: Array<{ key: string; value: string }> }>();
    getConfig.mockReturnValue(pending.promise);

    render(
      <ThemeAppearanceProvider>
        <PriceDirectionSync />
      </ThemeAppearanceProvider>,
    );

    applyPriceDirection('us', { persist: false });
    expect(document.documentElement).toHaveAttribute('data-price-direction', 'us');
    expect(localStorage.getItem(THEME_STORAGE_KEYS.priceDirection)).toBe('cn');

    await act(async () => {
      pending.resolve({
        items: [{ key: 'MARKET_REVIEW_COLOR_SCHEME', value: 'red_up' }],
      });
      await pending.promise;
    });

    expect(document.documentElement).toHaveAttribute('data-price-direction', 'us');
    expect(localStorage.getItem(THEME_STORAGE_KEYS.priceDirection)).toBe('cn');
  });
});
