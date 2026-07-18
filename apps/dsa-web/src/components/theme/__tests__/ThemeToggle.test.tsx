import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '../ThemeProvider';
import { ThemeToggle } from '../ThemeToggle';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-color-scheme: dark)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

describe('ThemeToggle', () => {
  it('opens the theme menu and shows all theme modes', async () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );

    const toggle = screen.getByRole('button', { name: '切换主题' });
    expect(toggle).toHaveClass('h-11', 'min-h-11', 'min-w-11');

    fireEvent.click(toggle);

    expect(await screen.findByRole('menu', { name: '主题模式' })).toBeInTheDocument();
    for (const option of screen.getAllByRole('menuitemradio')) {
      expect(option).toHaveClass('min-h-11');
    }
    const activeOption = screen.getAllByRole('menuitemradio').find(
      (option) => option.getAttribute('aria-checked') === 'true',
    );
    expect(activeOption).toHaveClass('bg-hover', 'text-foreground');
    expect(activeOption).not.toHaveClass('bg-primary/10');
    expect(screen.getByRole('menuitemradio', { name: '浅色' })).toBeInTheDocument();
    expect(screen.getByRole('menuitemradio', { name: '深色' })).toBeInTheDocument();
    expect(screen.getByRole('menuitemradio', { name: '跟随系统' })).toBeInTheDocument();
  });

  it('lays out the profile theme menu horizontally beside its trigger', () => {
    render(
      <ThemeProvider>
        <ThemeToggle menuLayout="horizontal" />
      </ThemeProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: '切换主题' }));

    const menu = screen.getByRole('menu', { name: '主题模式' });
    expect(menu).toHaveClass('grid', 'grid-cols-3', 'bottom-0', 'left-full');
  });
});
