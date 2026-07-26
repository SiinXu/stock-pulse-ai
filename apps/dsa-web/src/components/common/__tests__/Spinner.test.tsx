import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Spinner } from '../Spinner';

describe('Spinner', () => {
  it('is decorative by default', () => {
    const { container } = render(<Spinner size="sm" />);
    const spinner = container.querySelector('svg');

    expect(spinner).toHaveAttribute('aria-hidden', 'true');
    expect(spinner).toHaveAttribute('data-control', 'spinner');
    expect(spinner).not.toHaveAttribute('role');
    expect(spinner).toHaveClass('h-4', 'w-4', 'motion-reduce:animate-none');
  });

  it('announces a standalone loading state when labelled', () => {
    render(<Spinner size="lg" label="Loading report" />);

    const spinner = screen.getByRole('status', { name: 'Loading report' });
    expect(spinner).toHaveClass('h-6', 'w-6');
    expect(spinner).not.toHaveAttribute('aria-hidden');
  });
});
