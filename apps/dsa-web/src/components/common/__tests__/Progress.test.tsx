import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Progress } from '../Progress';

describe('Progress', () => {
  it('clamps determinate values and exposes progressbar semantics', () => {
    render(<Progress value={120} max={100} label="Analysis progress" valueText="Complete" />);

    const progress = screen.getByRole('progressbar', { name: 'Analysis progress' });
    expect(progress).toHaveAttribute('data-control', 'progress');
    expect(progress).toHaveAttribute('aria-valuemin', '0');
    expect(progress).toHaveAttribute('aria-valuemax', '100');
    expect(progress).toHaveAttribute('aria-valuenow', '100');
    expect(progress).toHaveAttribute('aria-valuetext', 'Complete');
    expect(progress.firstElementChild).toHaveStyle({ width: '100%' });
  });

  it('renders an indeterminate reduced-motion-safe state without a false value', () => {
    render(<Progress label="Connecting" />);

    const progress = screen.getByRole('progressbar', { name: 'Connecting' });
    expect(progress).not.toHaveAttribute('aria-valuenow');
    expect(progress).not.toHaveAttribute('aria-valuemin');
    expect(progress).not.toHaveAttribute('aria-valuemax');
    expect(progress.firstElementChild).toHaveClass('animate-pulse', 'motion-reduce:animate-none');
  });

  it('exposes semantic indicator tones without accepting internal geometry overrides', () => {
    render(<Progress value={40} label="Download progress" tone="primary" />);

    const indicator = screen.getByRole('progressbar', { name: 'Download progress' }).firstElementChild;
    expect(indicator).toHaveClass('bg-primary');
    expect(indicator).not.toHaveClass('bg-foreground');
  });
});
