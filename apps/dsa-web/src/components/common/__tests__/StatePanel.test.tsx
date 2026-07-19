import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatePanel } from '../StatePanel';

describe('StatePanel', () => {
  it('announces loading without relying on an animated class', () => {
    render(<StatePanel status="loading" title="Loading reports" description="Please wait" />);

    const panel = screen.getByRole('status');
    expect(panel).toHaveAttribute('aria-busy', 'true');
    expect(panel).toHaveAttribute('data-state', 'loading');
    expect(panel.querySelector('svg')).toHaveClass('motion-reduce:animate-none');
  });

  it('uses alert semantics only for errors', () => {
    const { rerender } = render(<StatePanel status="error" title="Could not load" />);
    expect(screen.getByRole('alert')).toHaveAttribute('data-state', 'error');

    rerender(<StatePanel status="disabled" title="Feature unavailable" />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('Feature unavailable').closest('[data-state]')).toHaveAttribute('data-state', 'disabled');
  });

  it('supports heading level, custom icon, and actions', () => {
    render(
      <StatePanel
        status="partial"
        title="Some data is delayed"
        titleAs="h2"
        icon={<span data-testid="custom-icon">!</span>}
        action={<button type="button">Retry</button>}
      />,
    );

    expect(screen.getByRole('heading', { level: 2, name: 'Some data is delayed' })).toBeInTheDocument();
    expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('renders empty states without adding a dashed card shell', () => {
    render(<StatePanel status="empty" title="No alerts" description="Create your first alert" />);

    const panel = screen.getByText('No alerts').closest('[data-state]');
    expect(panel).toHaveAttribute('data-state', 'empty');
    expect(panel).not.toHaveClass('border-dashed', 'shadow-soft-card', 'rounded-xl');
  });
});
