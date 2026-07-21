import { createRef } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, expectTypeOf, it } from 'vitest';
import { Button, type ButtonProps, type ButtonSize, type ButtonVariant } from '../Button';

describe('Button', () => {
  it('requires callers to declare an explicit intent', () => {
    type HasRequiredVariant = ButtonProps extends { variant: ButtonVariant } ? true : false;
    expectTypeOf<HasRequiredVariant>().toEqualTypeOf<true>();
  });

  it('keeps primitive variants free of page and module names', () => {
    expectTypeOf<ButtonVariant>().toEqualTypeOf<
      'primary' | 'secondary' | 'outline' | 'ghost' | 'danger' | 'danger-subtle'
    >();
  });

  it('exposes only semantic size tiers', () => {
    expectTypeOf<ButtonSize>().toEqualTypeOf<
      'compact' | 'default' | 'comfortable' | 'primary'
    >();
  });

  it('forwards its native ref and exposes the selected semantic contract', () => {
    const ref = createRef<HTMLButtonElement>();

    render(
      <Button ref={ref} variant="secondary" size="compact">
        Review
      </Button>,
    );

    const button = screen.getByRole('button', { name: 'Review' });
    expect(ref.current).toBe(button);
    expect(button).toHaveAttribute('data-control', 'button');
    expect(button).toHaveAttribute('data-variant', 'secondary');
    expect(button).toHaveAttribute('data-size', 'compact');
  });

  it.each([
    ['compact', 'h-5', 'rounded-md'],
    ['default', 'h-6', 'rounded-md'],
    ['comfortable', 'h-7', 'rounded-md'],
    ['primary', 'h-8', 'rounded-lg'],
  ] as const)(
    'exposes the selected %s geometry without changing its accessible name',
    (size, height, radius) => {
      render(<Button variant="secondary" size={size}>Action</Button>);

      const button = screen.getByRole('button', { name: 'Action' });
      expect(button).toHaveAttribute('data-size', size);
      expect(button).toHaveClass(height, radius);
    },
  );

  it('renders children under the requested intent', () => {
    render(<Button variant="secondary">Click me</Button>);

    const button = screen.getByRole('button', { name: 'Click me' });
    expect(button).toHaveAttribute('data-variant', 'secondary');
    expect(button).toHaveAttribute('data-size', 'comfortable');
    expect(button).toHaveClass('h-7', 'rounded-md');
  });

  it('uses button type by default and exposes the selected variant', () => {
    render(<Button variant="danger">Delete</Button>);

    const button = screen.getByRole('button', { name: 'Delete' });
    expect(button).toHaveAttribute('type', 'button');
    expect(button).toHaveAttribute('data-variant', 'danger');
  });

  it('keeps the action name stable while exposing busy state and loading text', () => {
    render(<Button variant="primary" isLoading loadingText="Saving">Save</Button>);

    const button = screen.getByRole('button', { name: 'Save' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(button).toHaveAccessibleName('Save');
    expect(screen.getByText('Saving')).toBeVisible();
  });

  it('supports the danger-subtle variant', () => {
    render(<Button variant="danger-subtle">Bulk Delete</Button>);

    const button = screen.getByRole('button', { name: 'Bulk Delete' });
    expect(button).toHaveAttribute('data-variant', 'danger-subtle');
  });
});
