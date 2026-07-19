import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ProfileMenu } from '../ProfileMenu';

const mockThemeToggle = vi.fn(({ menuLayout }: { menuLayout?: string }) => (
  <button type="button">Theme {menuLayout}</button>
));

vi.mock('../../theme/ThemeToggle', () => ({
  ThemeToggle: (props: { menuLayout?: string }) => mockThemeToggle(props),
}));

describe('ProfileMenu', () => {
  it('provides one compact mobile entry for theme and language', () => {
    render(<ProfileMenu variant="mobile" />);

    const trigger = screen.getByRole('button', { name: 'StockPulse' });
    expect(trigger).toHaveClass('h-11', 'w-11');
    fireEvent.click(trigger);

    const menu = screen.getByRole('menu', { name: 'StockPulse' });
    expect(within(menu).getByRole('button', { name: 'Theme vertical' })).toBeInTheDocument();
    expect(within(menu).getByRole('combobox', { name: '切换界面语言' })).toBeInTheDocument();
    expect(mockThemeToggle).toHaveBeenCalledWith(expect.objectContaining({ menuLayout: 'vertical' }));
  });

  it('keeps the sidebar theme picker horizontal', () => {
    render(<ProfileMenu variant="sidebar" />);
    fireEvent.click(screen.getByRole('button', { name: 'StockPulse' }));

    expect(screen.getByRole('button', { name: 'Theme horizontal' })).toBeInTheDocument();
  });
});
