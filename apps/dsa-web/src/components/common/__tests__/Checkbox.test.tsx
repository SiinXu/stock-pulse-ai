// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Checkbox } from '../Checkbox';

describe('Checkbox', () => {
  it('renders the 20px visual inside a 44px associated control target', () => {
    const onChange = vi.fn();
    render(<Checkbox label="Enable alerts" onChange={onChange} />);

    const checkbox = screen.getByRole('checkbox', { name: 'Enable alerts' });
    const hitTarget = checkbox.closest('label');

    expect(hitTarget).toHaveClass('min-h-11', 'min-w-11');
    expect(checkbox).toHaveClass('h-6', 'w-6');
    expect(checkbox.nextElementSibling).toHaveClass('inset-0.5');

    fireEvent.click(hitTarget!);
    expect(checkbox).toBeChecked();
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('provides the same minimum target when no visible label is supplied', () => {
    render(<Checkbox aria-label="Select row" />);

    expect(screen.getByRole('checkbox', { name: 'Select row' }).closest('label')).toHaveClass(
      'min-h-11',
      'min-w-11'
    );
  });

  it('forwards the native input ref for indeterminate selection states', () => {
    const ref = { current: null as HTMLInputElement | null };
    render(<Checkbox ref={ref} aria-label="Select all" />);

    expect(ref.current).toBe(screen.getByRole('checkbox', { name: 'Select all' }));
  });
});
