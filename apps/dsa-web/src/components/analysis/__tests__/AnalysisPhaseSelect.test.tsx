// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { AnalysisPhaseSelect } from '../AnalysisPhaseSelect';

if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

describe('AnalysisPhaseSelect', () => {
  it('exposes every backend-supported request phase with an accessible hint', () => {
    const onChange = vi.fn();
    render(
      <UiLanguageProvider initialLanguage="en">
        <AnalysisPhaseSelect
          id="phase"
          value="auto"
          onChange={onChange}
          label="Analysis phase"
          hint="Applies only to this request."
        />
      </UiLanguageProvider>,
    );

    const trigger = screen.getByRole('combobox', { name: 'Analysis phase' });
    expect(trigger).toHaveTextContent('Auto');
    expect(document.getElementById(trigger.getAttribute('aria-describedby')!))
      .toHaveTextContent('Applies only to this request.');

    fireEvent.click(trigger);
    const listbox = screen.getByRole('listbox');
    expect(within(listbox).getAllByRole('option').map((option) => option.textContent))
      .toEqual(['Auto', 'Pre-market', 'Intraday', 'Post-market']);
    fireEvent.click(within(listbox).getByRole('option', { name: 'Intraday' }));

    expect(onChange).toHaveBeenCalledWith('intraday');
  });
});
