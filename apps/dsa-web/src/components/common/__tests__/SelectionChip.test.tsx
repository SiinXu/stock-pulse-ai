// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, expectTypeOf, it, vi } from 'vitest';
import { SelectionChip, type SelectionChipProps } from '../SelectionChip';

describe('SelectionChip', () => {
  it('keeps geometry and presentation inside the primitive API', () => {
    type HasClassName = 'className' extends keyof SelectionChipProps ? true : false;
    type HasStyle = 'style' extends keyof SelectionChipProps ? true : false;
    type HasType = 'type' extends keyof SelectionChipProps ? true : false;
    type HasAriaBusy = 'aria-busy' extends keyof SelectionChipProps ? true : false;

    expectTypeOf<HasClassName>().toEqualTypeOf<false>();
    expectTypeOf<HasStyle>().toEqualTypeOf<false>();
    expectTypeOf<HasType>().toEqualTypeOf<false>();
    expectTypeOf<HasAriaBusy>().toEqualTypeOf<false>();
  });

  it('forwards its ref and remains a non-submitting native button', () => {
    const ref = createRef<HTMLButtonElement>();
    render(<SelectionChip ref={ref} label="AAPL Apple" />);

    const chip = screen.getByRole('button', { name: 'AAPL Apple' });
    expect(ref.current).toBe(chip);
    expect(chip).toHaveAttribute('type', 'button');
    expect(chip).toHaveAttribute('data-control', 'selection-chip');
    expect(chip).not.toHaveAttribute('aria-pressed');
    expect(chip).not.toHaveAttribute('data-selected');
  });

  it('exposes persistent selected and unselected state without changing the name', () => {
    const { rerender } = render(
      <SelectionChip selected label="AAPL Apple Incorporated" />,
    );

    const chip = screen.getByRole('button', { name: 'AAPL Apple Incorporated' });
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    expect(chip).toHaveAttribute('data-selected', 'true');

    rerender(<SelectionChip selected={false} label="AAPL Apple Incorporated" />);
    expect(chip).toHaveAttribute('aria-pressed', 'false');
    expect(chip).toHaveAttribute('data-selected', 'false');
    expect(chip).toHaveAccessibleName('AAPL Apple Incorporated');
  });

  it('allows multi-part, multi-line content under one accessible command', () => {
    render(
      <SelectionChip
        label={<span>BRK.B</span>}
        description="Berkshire Hathaway Incorporated Class B Common Stock"
        metadata="/ NYSE"
      />,
    );

    expect(screen.getByRole('button', {
      name: 'BRK.B Berkshire Hathaway Incorporated Class B Common Stock / NYSE',
    })).toBeVisible();
    expect(screen.getByText(/Berkshire Hathaway Incorporated/)).toBeVisible();
  });

  it('preserves native activation and disabled behavior', () => {
    const onSelect = vi.fn();
    const { rerender } = render(
      <SelectionChip onClick={onSelect} label="Select MSFT" />,
    );

    const chip = screen.getByRole('button', { name: 'Select MSFT' });
    fireEvent.click(chip);
    expect(onSelect).toHaveBeenCalledTimes(1);

    rerender(<SelectionChip onClick={onSelect} disabled label="Select MSFT" />);
    expect(chip).toBeDisabled();
    fireEvent.click(chip);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it('owns a non-activating loading state without changing the accessible name', () => {
    const onSelect = vi.fn();
    const { rerender } = render(
      <SelectionChip isLoading onClick={onSelect} label="Synchronize candidate" />,
    );

    const chip = screen.getByRole('button', { name: 'Synchronize candidate' });
    expect(chip).toBeDisabled();
    expect(chip).toHaveAttribute('aria-busy', 'true');
    expect(chip).toHaveAttribute('data-loading', 'true');
    expect(chip.querySelector('[data-indicator="loading"]')).not.toBeNull();
    fireEvent.click(chip);
    expect(onSelect).not.toHaveBeenCalled();

    rerender(<SelectionChip onClick={onSelect} label="Synchronize candidate" />);
    expect(chip).toBeEnabled();
    expect(chip).not.toHaveAttribute('aria-busy');
    expect(chip).not.toHaveAttribute('data-loading');
    expect(chip.querySelector('[data-indicator="loading"]')).toBeNull();
  });
});
