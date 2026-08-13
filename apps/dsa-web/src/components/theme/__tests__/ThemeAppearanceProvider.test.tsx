// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { THEME_STORAGE_KEYS } from '../../../design/theme';
import { SidebarProfile } from '../../layout/SidebarProfile';
import { ThemeAppearanceProvider } from '../ThemeAppearanceProvider';

describe('ThemeAppearanceProvider production reachability', () => {
  beforeEach(() => {
    document.documentElement.removeAttribute('data-theme-pack');
    document.documentElement.removeAttribute('data-price-direction');
    localStorage.removeItem(THEME_STORAGE_KEYS.pack);
    localStorage.removeItem(THEME_STORAGE_KEYS.priceDirection);
  });

  it('lets a user select and persist a theme pack from the sidebar profile', () => {
    render(
      <ThemeAppearanceProvider>
        <SidebarProfile open />
      </ThemeAppearanceProvider>,
    );

    fireEvent.click(screen.getByRole('combobox', { name: '主题 · Classic' }));
    fireEvent.click(screen.getByRole('option', { name: 'Slate' }));

    expect(screen.getByRole('combobox', { name: '主题 · Slate' })).toHaveAttribute(
      'data-value',
      'slate',
    );
    expect(document.documentElement).toHaveAttribute('data-theme-pack', 'slate');
    expect(localStorage.getItem(THEME_STORAGE_KEYS.pack)).toBe('slate');
  });
});
