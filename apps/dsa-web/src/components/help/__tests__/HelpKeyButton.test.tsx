// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { EDUCATION_HELP_KEYS } from '../../../locales/educationHelpKeys';
import { HelpKeyButton } from '../HelpKeyButton';

function renderHelp(helpKey: string) {
  render(
    <UiLanguageProvider>
      <HelpKeyButton helpKey={helpKey} data-testid="edu-help" />
    </UiLanguageProvider>,
  );
  return screen.getByTestId('edu-help');
}

describe('HelpKeyButton', () => {
  it('renders three-part plain-language risk level help from settings-help inventory', () => {
    const trigger = renderHelp(EDUCATION_HELP_KEYS.riskLevelCritical);
    fireEvent.mouseEnter(trigger.parentElement!);

    const tooltip = screen.getByRole('tooltip');
    expect(tooltip).toHaveTextContent(/0–100|0-100|75/);
    expect(tooltip).toHaveTextContent(/是什么|What it is/);
    expect(tooltip).toHaveTextContent(/为什么|Why it matters/);
    expect(tooltip).toHaveTextContent(/对你意味着什么|What it means for you/);
  });

  it('renders indicator MACD help without hardcoding body copy in the component', () => {
    const trigger = renderHelp(EDUCATION_HELP_KEYS.indicatorMacd);
    fireEvent.mouseEnter(trigger.parentElement!);

    const tooltip = screen.getByRole('tooltip');
    expect(tooltip).toHaveTextContent(/MACD|12\/26\/9|动量/);
  });

  it('returns null for unknown help keys', () => {
    const { container } = render(
      <UiLanguageProvider>
        <HelpKeyButton helpKey="education.missing.key" />
      </UiLanguageProvider>,
    );
    expect(container.querySelector('[data-help-key]')).toBeNull();
  });
});
