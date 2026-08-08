// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SettingsModeToggle } from '../SettingsModeToggle';

describe('SettingsModeToggle', () => {
  it('renders Essentials and Expert options and reports mode changes', () => {
    const onModeChange = vi.fn();
    render(
      <SettingsModeToggle
        mode="essentials"
        onModeChange={onModeChange}
        language="en"
      />,
    );
    expect(screen.getByTestId('settings-mode-toggle')).toBeInTheDocument();
    expect(screen.getByText('Settings mode')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'Expert' }));
    expect(onModeChange).toHaveBeenCalledWith('expert');
  });

  it('marks the active mode as selected', () => {
    render(
      <SettingsModeToggle
        mode="expert"
        onModeChange={() => {}}
        language="en"
      />,
    );
    expect(screen.getByRole('radio', { name: 'Expert' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: 'Essentials' })).toHaveAttribute('aria-checked', 'false');
  });
});
