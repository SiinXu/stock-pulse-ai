import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(toggle);

    expect(await screen.findByRole('menu', { name: '主题模式' })).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getAllByRole('menuitemradio')).toHaveLength(3);
    expect(screen.getByRole('menuitemradio', { name: '浅色' })).toBeInTheDocument();
    expect(screen.getByRole('menuitemradio', { name: '深色' })).toBeInTheDocument();
    expect(screen.getByRole('menuitemradio', { name: '跟随系统' })).toBeInTheDocument();
    expect(screen.getAllByRole('menuitemradio').filter((option) => (
      option.getAttribute('aria-checked') === 'true'
    ))).toHaveLength(1);
  });

  it('keeps the horizontal profile menu portalled and keyboard navigable', async () => {
    render(
      <ThemeProvider>
        <ThemeToggle menuLayout="horizontal" />
      </ThemeProvider>,
    );

    const trigger = screen.getByRole('button', { name: '切换主题' });
    const triggerContainer = trigger.parentElement;
    fireEvent.click(trigger);

    const menu = screen.getByRole('menu', { name: '主题模式' });
    expect(document.body).toContainElement(menu);
    expect(triggerContainer).not.toContainElement(menu);

    const options = screen.getAllByRole('menuitemradio');
    await waitFor(() => expect(options).toContain(document.activeElement));
    const currentIndex = options.indexOf(document.activeElement as HTMLElement);
    fireEvent.keyDown(menu, { key: 'ArrowRight' });
    expect(options[(currentIndex + 1) % options.length]).toHaveFocus();
  });
});
