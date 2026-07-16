import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Checkbox } from '../Checkbox';

describe('Checkbox', () => {
  it('keeps the compact visual inside a 44px associated label target', () => {
    const onChange = vi.fn();
    render(<Checkbox label="Enable alerts" onChange={onChange} />);

    const checkbox = screen.getByRole('checkbox', { name: 'Enable alerts' });
    const hitTarget = checkbox.closest('label');

    expect(hitTarget).toHaveClass('min-h-11', 'min-w-11');
    expect(checkbox).toHaveClass('h-4', 'w-4');

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
});
