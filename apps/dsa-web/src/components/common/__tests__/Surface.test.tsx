import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Card } from '../Card';
import { Surface } from '../Surface';

describe('Surface', () => {
  it('forwards its ref and exposes distinct bordered and elevated levels', () => {
    const ref = { current: null as HTMLDivElement | null };
    const { rerender } = render(
      <Surface ref={ref} variant="bordered" data-testid="surface">Content</Surface>,
    );

    expect(ref.current).toBe(screen.getByTestId('surface'));
    expect(ref.current).toHaveClass('border', 'bg-card');
    expect(ref.current).not.toHaveClass('shadow-soft-card');

    rerender(<Surface ref={ref} variant="elevated" data-testid="surface">Content</Surface>);
    expect(ref.current).toHaveClass('shadow-soft-card');
  });

  it('maps legacy Card variants to distinct Surface levels', () => {
    const { rerender } = render(<Card variant="default">Default</Card>);
    expect(screen.getByText('Default')).toHaveClass('shadow-soft-card');

    rerender(<Card variant="bordered">Bordered</Card>);
    expect(screen.getByText('Bordered')).toHaveClass('border');
    expect(screen.getByText('Bordered')).not.toHaveClass('terminal-card');
  });
});
