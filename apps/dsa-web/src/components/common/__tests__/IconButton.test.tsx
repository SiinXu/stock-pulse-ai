import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { IconButton } from '../IconButton';

describe('IconButton', () => {
  it('keeps a 44px target around a compact visual and exposes a tooltip', () => {
    render(<IconButton aria-label="Close panel">x</IconButton>);

    const button = screen.getByRole('button', { name: 'Close panel' });
    expect(button).toHaveClass('h-11', 'w-11');
    expect(button.firstElementChild).toHaveClass('h-8', 'w-8');

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

  it('keeps the 44px target for a 20px compact visual', () => {
    render(
      <IconButton aria-label="Delete item" visualSize="xs" tooltip={false}>
        x
      </IconButton>,
    );

    const button = screen.getByRole('button', { name: 'Delete item' });
    expect(button).toHaveClass('h-11', 'w-11');
    expect(button.firstElementChild).toHaveClass('h-5', 'w-5');
  });
});
