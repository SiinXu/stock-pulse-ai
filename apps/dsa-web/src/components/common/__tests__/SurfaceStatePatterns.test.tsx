import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  Alert,
  Card,
  EmptyState,
  InlineAlert,
  Section,
  StatePanel,
  Surface,
} from '..';

describe('Surface', () => {
  it('forwards native attributes and exposes the semantic surface level', () => {
    const ref = createRef<HTMLElement>();

    render(
      <Surface
        ref={ref}
        as="article"
        level="section"
        padding="md"
        data-testid="surface"
        aria-label="Analysis summary"
      >
        Summary
      </Surface>,
    );

    const surface = screen.getByTestId('surface');
    expect(surface.tagName).toBe('ARTICLE');
    expect(surface).toHaveAttribute('data-surface-level', 'section');
    expect(surface).toHaveAccessibleName('Analysis summary');
    expect(ref.current).toBe(surface);
  });
});

describe('Section', () => {
  it('associates its visible heading with the semantic section', () => {
    const ref = createRef<HTMLElement>();

    render(
      <Section
        ref={ref}
        title="Portfolio risk"
        description="Current concentration and drawdown"
        actions={<button type="button">Refresh</button>}
      >
        <p>Section content</p>
      </Section>,
    );

    const section = screen.getByRole('region', { name: 'Portfolio risk' });
    expect(section.tagName).toBe('SECTION');
    expect(section).toHaveAttribute('data-pattern', 'section');
    expect(section).toHaveAttribute('data-surface-level', 'canvas');
    expect(screen.getByRole('heading', { level: 2, name: 'Portfolio risk' })).toBeInTheDocument();
    expect(screen.getByText('Current concentration and drawdown')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument();
    expect(ref.current).toBe(section);
  });
});

describe('StatePanel', () => {
  it('uses typed state semantics without making a persistent empty state live', () => {
    const { rerender } = render(
      <StatePanel state="empty" title="No reports" description="Run an analysis to create one." />,
    );

    const empty = screen.getByText('No reports').closest('[data-state-panel]');
    expect(empty).toHaveAttribute('data-state-panel', 'empty');
    expect(empty).not.toHaveAttribute('role');

    rerender(<StatePanel state="loading" title="Loading reports" />);
    const loading = screen.getByRole('status');
    expect(loading).toHaveAttribute('data-state-panel', 'loading');
    expect(loading).toHaveAttribute('aria-busy', 'true');
    expect(loading).toHaveAttribute('aria-live', 'polite');

    rerender(<StatePanel state="error" title="Reports unavailable" />);
    const error = screen.getByRole('alert');
    expect(error).toHaveAttribute('data-state-panel', 'error');
    expect(error).toHaveAttribute('aria-live', 'assertive');
  });
});

describe('Alert', () => {
  it('forwards its ref and gives dismiss and action controls explicit semantics', () => {
    const onDismiss = vi.fn();
    const onRetry = vi.fn();
    const ref = createRef<HTMLDivElement>();

    render(
      <Alert
        ref={ref}
        tone="danger"
        title="Request failed"
        dismissLabel="Dismiss request error"
        onDismiss={onDismiss}
        action={<button type="button" onClick={onRetry}>Retry request</button>}
      >
        The service could not be reached.
      </Alert>,
    );

    const alert = screen.getByRole('alert');
    expect(alert).toHaveAttribute('data-alert-tone', 'danger');
    expect(ref.current).toBe(alert);

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss request error' }));
    fireEvent.click(screen.getByRole('button', { name: 'Retry request' }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

describe('legacy surface and state adapters', () => {
  it('maps existing components onto the authoritative contracts', () => {
    const { rerender } = render(
      <Card data-testid="card">Card content</Card>,
    );

    expect(screen.getByTestId('card')).toHaveAttribute('data-surface-level', 'section');

    rerender(<Card data-testid="card" variant="bordered">Card content</Card>);
    expect(screen.getByTestId('card')).toHaveAttribute('data-surface-level', 'interactive');

    rerender(<EmptyState title="Nothing here" />);
    expect(screen.getByText('Nothing here').closest('[data-state-panel]')).toHaveAttribute('data-state-panel', 'empty');

    rerender(<InlineAlert variant="warning" message="Review the current values." />);
    expect(screen.getByRole('status')).toHaveAttribute('data-alert-tone', 'warning');
  });
});
