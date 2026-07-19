// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { SettingsHelpButton } from '../SettingsHelpButton';

function renderHelpButton() {
  render(
    <UiLanguageProvider>
      <SettingsHelpButton
        fieldKey="STOCK_LIST"
        title="Watchlist"
        helpKey="settings.base.STOCK_LIST"
      />
    </UiLanguageProvider>,
  );
  return screen.getByRole('button', { name: /Watchlist/ });
}

describe('SettingsHelpButton tooltip contract', () => {
  it('shows only the field purpose and recommendation in the shared tooltip', () => {
    const trigger = renderHelpButton();

    fireEvent.mouseEnter(trigger.parentElement!);

    const tooltip = screen.getByRole('tooltip');
    expect(tooltip).toHaveTextContent('Defines the stock codes used by analysis jobs and notification reports.');
    expect(tooltip).toHaveTextContent('Saved STOCK_LIST values are written with English commas.');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('supports keyboard focus and closes the tooltip on Escape', () => {
    const trigger = renderHelpButton();

    fireEvent.focus(trigger);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();

    fireEvent.keyDown(trigger.parentElement!, { key: 'Escape' });
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
});
