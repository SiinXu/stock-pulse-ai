import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Pagination } from '../Pagination';

// No UiLanguageProvider wrapper: useUiLanguage falls back to the zh context,
// keeping label assertions deterministic regardless of the jsdom locale.

describe('Pagination', () => {
  it('renders nothing for a single page', () => {
    const { container } = render(
      <Pagination currentPage={1} totalPages={1} onPageChange={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('exposes a navigation landmark with labeled prev/next controls', () => {
    render(<Pagination currentPage={2} totalPages={5} onPageChange={vi.fn()} />);

    expect(screen.getByRole('navigation', { name: '分页导航' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '上一页' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '下一页' })).toBeEnabled();
  });

  it('marks only the active page with aria-current', () => {
    render(<Pagination currentPage={3} totalPages={5} onPageChange={vi.fn()} />);

    const current = screen.getByRole('button', { name: '3' });
    expect(current).toHaveAttribute('aria-current', 'page');

    const other = screen.getByRole('button', { name: '2' });
    expect(other).not.toHaveAttribute('aria-current');
  });

  it('disables prev on the first page and next on the last page', () => {
    const { rerender } = render(
      <Pagination currentPage={1} totalPages={5} onPageChange={vi.fn()} />,
    );
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled();

    rerender(<Pagination currentPage={5} totalPages={5} onPageChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled();
  });
});
