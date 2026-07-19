import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Switch } from '../Switch';

describe('Switch', () => {
  it('uses a 44px target around the shared 40x24 visual track', () => {
    render(<Switch checked={false} onCheckedChange={() => {}} aria-label="Realtime quotes" />);

    const control = screen.getByRole('switch', { name: 'Realtime quotes' });
    expect(control).toHaveClass('h-11', 'w-11');
    expect(control.firstElementChild).toHaveClass('h-6', 'w-10');
    expect(control).toHaveAttribute('data-state', 'unchecked');
  });

  it('toggles through native button activation and forwards its ref', () => {
    const onCheckedChange = vi.fn();
    const ref = { current: null as HTMLButtonElement | null };
    render(
      <Switch
        ref={ref}
        checked
        onCheckedChange={onCheckedChange}
        aria-label="Enabled"
      />,
    );

    const control = screen.getByRole('switch', { name: 'Enabled' });
    expect(ref.current).toBe(control);
    expect(control).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(control);
    expect(onCheckedChange).toHaveBeenCalledWith(false);
  });

  it('does not toggle while disabled', () => {
    const onCheckedChange = vi.fn();
    render(
      <Switch disabled checked={false} onCheckedChange={onCheckedChange} aria-label="Disabled" />,
    );

    fireEvent.click(screen.getByRole('switch', { name: 'Disabled' }));
    expect(onCheckedChange).not.toHaveBeenCalled();
  });
});
