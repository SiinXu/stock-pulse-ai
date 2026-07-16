import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Button } from '../Button';

describe('Button', () => {
  it.each(['xsm', 'sm', 'md', 'lg', 'xl'] as const)(
    'keeps the %s variant at least 44px in both dimensions at every breakpoint',
    (size) => {
      render(<Button size={size}>Action</Button>);

      const button = screen.getByRole('button', { name: 'Action' });
      expect(button).toHaveClass('min-h-11', 'min-w-11');
      expect(button).not.toHaveClass('sm:min-h-0');
    },
  );

  it('provides a stable 44px square size for icon-only actions', () => {
    render(<Button size="icon" aria-label="Open details">+</Button>);

    expect(screen.getByRole('button', { name: 'Open details' })).toHaveClass(
      'h-11',
      'min-h-11',
      'w-11',
      'min-w-11',
      'p-0',
    );
  });

  it('renders children', () => {
    render(<Button>Click me</Button>);

    expect(screen.getByRole('button', { name: 'Click me' })).toBeInTheDocument();
  });

  it('uses button type by default and exposes the selected variant', () => {
    render(<Button variant="danger">Delete</Button>);

    const button = screen.getByRole('button', { name: 'Delete' });
    expect(button).toHaveAttribute('type', 'button');
    expect(button).toHaveAttribute('data-variant', 'danger');
    expect(button.className).toContain('bg-danger');
  });

  it('disables the button when loading and shows loading text', () => {
    render(<Button isLoading loadingText="Saving">Save</Button>);

    const button = screen.getByRole('button', { name: /saving/i });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('Saving')).toBeInTheDocument();
  });

  it('keeps icon loading states spinner-only without losing accessibility metadata', () => {
    render(
      <Button size="icon" isLoading loadingText="Saving" aria-label="Save item">
        Save
      </Button>,
    );

    const button = screen.getByRole('button', { name: 'Save item' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(button.textContent).toBe('');
    expect(button.querySelector('svg.animate-spin')).toBeInTheDocument();
    expect(button.querySelector('svg.animate-spin')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.queryByText('Saving')).not.toBeInTheDocument();
  });

  it('supports the danger-subtle variant', () => {
    render(<Button variant="danger-subtle">Bulk Delete</Button>);

    const button = screen.getByRole('button', { name: 'Bulk Delete' });
    expect(button).toHaveAttribute('data-variant', 'danger-subtle');
    expect(button.className).toContain('border-danger/50');
    expect(button.className).toContain('bg-danger/10');
  });

  it.each([
    ['action-primary', '--home-action-ai-bg', '--home-action-ai-border', '--home-action-ai-text'],
    ['action-secondary', '--home-action-report-bg', '--home-action-report-border', '--home-action-report-text'],
  ] as const)('supports the %s variant', (variant, bgToken, borderToken, textToken) => {
    render(<Button variant={variant}>Quick Action</Button>);

    const button = screen.getByRole('button', { name: 'Quick Action' });
    expect(button).toHaveAttribute('data-variant', variant);
    expect(button.className).toContain(bgToken);
    expect(button.className).toContain(borderToken);
    expect(button.className).toContain(textToken);
  });
});
