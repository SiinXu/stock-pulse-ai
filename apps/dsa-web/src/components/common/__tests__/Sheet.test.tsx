// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { FilterSheet } from '../Sheet';

describe('FilterSheet', () => {
  it('keeps actions reachable outside the scrollable body and restores focus', () => {
    const onApply = vi.fn();
    const Harness = () => {
      const [open, setOpen] = useState(false);
      return (
        <UiLanguageProvider>
          <button type="button" onClick={() => setOpen(true)}>More filters</button>
          <FilterSheet
            isOpen={open}
            onClose={() => setOpen(false)}
            title="More filters"
            resetLabel="Reset"
            applyLabel="View 12 results"
            onReset={() => undefined}
            onApply={onApply}
          >
            <label htmlFor="market-filter">Market</label>
            <input id="market-filter" />
          </FilterSheet>
        </UiLanguageProvider>
      );
    };

    render(<Harness />);
    const trigger = screen.getByRole('button', { name: 'More filters' });
    trigger.focus();
    fireEvent.click(trigger);

    const sheet = screen.getByRole('dialog', { name: 'More filters' });
    expect(sheet.querySelector('[data-overlay-slot="body"]')).toContainElement(
      screen.getByRole('textbox', { name: 'Market' }),
    );
    expect(sheet.querySelector('[data-overlay-slot="footer"]')).toContainElement(
      screen.getByRole('button', { name: 'View 12 results' }),
    );
    expect(document.body.style.overflow).toBe('hidden');

    fireEvent.click(screen.getByRole('button', { name: 'View 12 results' }));
    expect(onApply).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(sheet, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'More filters' })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
