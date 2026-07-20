// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { AdvancedFilterSheet } from '../AdvancedFilterSheet';
import { AppliedFilterChips } from '../AppliedFilterChips';
import { FilterBar } from '../FilterBar';

function setDesktopViewport(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe('Filter patterns', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('owns form submission and blocks disabled or in-flight Apply actions', () => {
    const onApply = vi.fn();
    const renderBar = (applyDisabled: boolean, isApplying: boolean) => (
      <UiLanguageProvider>
        <FilterBar
          aria-label="Signal filters"
          applyLabel="Apply filters"
          loadingLabel="Applying filters"
          onApply={onApply}
          applyDisabled={applyDisabled}
          isApplying={isApplying}
          advanced={<button type="button">More filters</button>}
        >
          <input aria-label="Stock code" />
        </FilterBar>
      </UiLanguageProvider>
    );

    const { rerender } = render(renderBar(false, false));
    const form = screen.getByRole('form', { name: 'Signal filters' });
    fireEvent.submit(form);
    expect(onApply).toHaveBeenCalledTimes(1);

    rerender(renderBar(true, false));
    expect(screen.getByRole('button', { name: 'Apply filters' })).toBeDisabled();
    fireEvent.submit(form);
    expect(onApply).toHaveBeenCalledTimes(1);

    rerender(renderBar(false, true));
    expect(screen.getByRole('button', { name: 'Apply filters' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Apply filters' })).toHaveAttribute('aria-busy', 'true');
    fireEvent.submit(form);
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it('exposes applied filters as individually removable chips with one clear-all command', () => {
    const onRemoveMarket = vi.fn();
    const onRemoveStatus = vi.fn();
    const onClearAll = vi.fn();
    render(
      <UiLanguageProvider>
        <AppliedFilterChips
          aria-label="Applied filters"
          clearAllLabel="Clear all filters"
          onClearAll={onClearAll}
          filters={[
            {
              id: 'market',
              label: 'Market',
              value: 'US',
              removeLabel: 'Remove Market filter',
              onRemove: onRemoveMarket,
            },
            {
              id: 'status',
              label: 'Status',
              value: 'Closed',
              removeLabel: 'Remove Status filter',
              onRemove: onRemoveStatus,
            },
          ]}
        />
      </UiLanguageProvider>,
    );

    expect(screen.getByRole('list', { name: 'Applied filters' })).toBeVisible();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'Remove Market filter' }));
    fireEvent.click(screen.getByRole('button', { name: 'Clear all filters' }));
    expect(onRemoveMarket).toHaveBeenCalledTimes(1);
    expect(onRemoveStatus).not.toHaveBeenCalled();
    expect(onClearAll).toHaveBeenCalledTimes(1);
  });

  it('uses a bottom Sheet on mobile and restores trigger focus after Apply', async () => {
    setDesktopViewport(false);
    const onReset = vi.fn();
    const onApply = vi.fn(() => true);
    render(
      <UiLanguageProvider>
        <AdvancedFilterSheet
          triggerLabel="More filters"
          triggerAriaLabel="More filters, 2 active"
          activeCount={2}
          title="More filters"
          description="Refine signals"
          resetLabel="Reset"
          applyLabel="View 12 results"
          onReset={onReset}
          onApply={onApply}
        >
          <input aria-label="Market" />
        </AdvancedFilterSheet>
      </UiLanguageProvider>,
    );

    const trigger = screen.getByRole('button', { name: 'More filters, 2 active' });
    trigger.focus();
    fireEvent.click(trigger);
    const sheet = screen.getByRole('dialog', { name: 'More filters' });
    expect(sheet).toHaveAttribute('aria-modal', 'true');
    expect(sheet.querySelector('[data-overlay-slot="footer"]')).toContainElement(
      screen.getByRole('button', { name: 'View 12 results' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
    fireEvent.click(screen.getByRole('button', { name: 'View 12 results' }));
    expect(onReset).toHaveBeenCalledTimes(1);
    expect(onApply).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'More filters' })).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it('uses a non-modal Popover on desktop and keeps invalid drafts open', async () => {
    setDesktopViewport(true);
    const onApply = vi.fn(() => false);
    render(
      <UiLanguageProvider>
        <AdvancedFilterSheet
          triggerLabel="More filters"
          triggerAriaLabel="More filters"
          activeCount={0}
          title="More filters"
          resetLabel="Reset"
          applyLabel="View results"
          onReset={() => undefined}
          onApply={onApply}
        >
          <input aria-label="Market" />
        </AdvancedFilterSheet>
      </UiLanguageProvider>,
    );

    const trigger = screen.getByRole('button', { name: 'More filters' });
    fireEvent.click(trigger);
    const popover = await screen.findByRole('dialog', { name: 'More filters' });
    expect(popover).not.toHaveAttribute('aria-modal');
    expect(trigger).toHaveAttribute('aria-controls', popover.id);
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Market' })).toHaveFocus());
    fireEvent.click(screen.getByRole('button', { name: 'View results' }));
    expect(onApply).toHaveBeenCalledTimes(1);
    expect(popover).toBeVisible();
  });

  it.each([
    { label: 'mobile Sheet', desktop: false },
    { label: 'desktop Popover', desktop: true },
  ])('contains advanced Apply submission inside its $label form boundary', async ({ desktop }) => {
    setDesktopViewport(desktop);
    const onPrimaryApply = vi.fn();
    const onAdvancedApply = vi.fn(() => true);
    render(
      <UiLanguageProvider>
        <FilterBar
          aria-label="Signal filters"
          applyLabel="Apply filters"
          onApply={onPrimaryApply}
          advanced={(
            <AdvancedFilterSheet
              triggerLabel="More filters"
              triggerAriaLabel="More filters"
              activeCount={0}
              title="More filters"
              resetLabel="Reset"
              applyLabel="View results"
              onReset={() => undefined}
              onApply={onAdvancedApply}
            >
              <input aria-label="Market" />
            </AdvancedFilterSheet>
          )}
        >
          <input aria-label="Stock code" />
        </FilterBar>
      </UiLanguageProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'More filters' }));
    const dialog = await screen.findByRole('dialog', { name: 'More filters' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'View results' }));

    expect(onAdvancedApply).toHaveBeenCalledTimes(1);
    expect(onPrimaryApply).not.toHaveBeenCalled();
  });
});
