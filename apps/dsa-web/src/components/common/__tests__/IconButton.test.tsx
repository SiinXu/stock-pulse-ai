import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { RefreshCw } from 'lucide-react';
import { describe, expect, it } from 'vitest';
import { IconButton } from '../IconButton';

describe('IconButton', () => {
  it('forwards its native ref and exposes an accessible visual-size contract', () => {
    const ref = createRef<HTMLButtonElement>();

    render(
      <IconButton ref={ref} aria-label="Refresh analysis" size="compact" tooltip={false}>
        <RefreshCw aria-hidden="true" />
      </IconButton>,
    );

    const button = screen.getByRole('button', { name: 'Refresh analysis' });
    expect(ref.current).toBe(button);
    expect(button).toHaveAttribute('type', 'button');
    expect(button).toHaveAttribute('data-control', 'icon-button');
    expect(button).toHaveAttribute('data-size', 'compact');
  });

  it('keeps its accessible name and disables duplicate actions while loading', () => {
    render(
      <IconButton aria-label="Refresh analysis" isLoading tooltip={false}>
        <RefreshCw aria-hidden="true" />
      </IconButton>,
    );

    const button = screen.getByRole('button', { name: 'Refresh analysis' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
  });

  it('associates its visible tooltip with the focused button', async () => {
    render(
      <IconButton aria-label="Refresh analysis">
        <RefreshCw aria-hidden="true" />
      </IconButton>,
    );

    const button = screen.getByRole('button', { name: 'Refresh analysis' });
    fireEvent.focus(button);
    const tooltip = await screen.findByRole('tooltip');

    expect(button).toHaveAttribute('aria-describedby', tooltip.id);
    fireEvent.keyDown(button, { key: 'Escape' });
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
});
