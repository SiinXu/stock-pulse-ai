import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { IconButton } from '../IconButton';

describe('IconButton', () => {
  it('matches the compact visual size and exposes a tooltip', () => {
    render(<IconButton aria-label="Close panel">x</IconButton>);

    const button = screen.getByRole('button', { name: 'Close panel' });
    expect(button).toHaveClass('h-7', 'w-7');
    expect(button.firstElementChild).toHaveClass('h-7', 'w-7');

    fireEvent.mouseEnter(button.parentElement!);
    expect(screen.getByRole('tooltip')).toHaveTextContent('Close panel');
  });

  it('forwards its ref and preserves pressed state', () => {
    const ref = { current: null as HTMLButtonElement | null };
    render(
      <IconButton ref={ref} aria-label="Pin panel" aria-pressed tooltip={false}>
        p
      </IconButton>,
    );

    const button = screen.getByRole('button', { name: 'Pin panel' });
    expect(ref.current).toBe(button);
    expect(button).toHaveAttribute('aria-pressed', 'true');
  });

  it('disables while loading without replacing its accessible name', () => {
    render(<IconButton aria-label="Refresh data" isLoading>r</IconButton>);

    const button = screen.getByRole('button', { name: 'Refresh data' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(button.querySelector('svg.animate-spin')).toBeInTheDocument();
  });

  it('uses a 20px target for the extra-small visual', () => {
    render(
      <IconButton aria-label="Delete item" visualSize="xs" tooltip={false}>
        x
      </IconButton>,
    );

    const button = screen.getByRole('button', { name: 'Delete item' });
    expect(button).toHaveClass('h-5', 'w-5');
    expect(button.firstElementChild).toHaveClass('h-5', 'w-5');
  });
});
