// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Pagination } from '../Pagination';

// No UiLanguageProvider wrapper: useUiLanguage falls back to the zh context,
// keeping label assertions deterministic regardless of the jsdom locale.

function pageNumberLabels(nav: HTMLElement): string[] {
  return within(nav)
    .getAllByRole('button')
    .map((btn) => btn.getAttribute('aria-label') || btn.textContent || '')
    .filter((label) => label !== '上一页' && label !== '下一页');
}

describe('Pagination', () => {
  it('renders nothing for a single page', () => {
    const { container } = render(
      <Pagination currentPage={1} totalPages={1} onPageChange={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('exposes a navigation landmark with labeled prev/next controls', () => {
    render(<Pagination currentPage={2} totalPages={5} onPageChange={vi.fn()} density="full" />);

    expect(screen.getByRole('navigation', { name: '分页导航' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '上一页' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '下一页' })).toBeEnabled();
  });

  it('marks only the active page with aria-current', () => {
    render(<Pagination currentPage={3} totalPages={5} onPageChange={vi.fn()} density="full" />);

    const current = screen.getByRole('button', { name: '3' });
    expect(current).toHaveAttribute('aria-current', 'page');

    const other = screen.getByRole('button', { name: '2' });
    expect(other).not.toHaveAttribute('aria-current');
  });

  it('disables prev on the first page and next on the last page', () => {
    const { rerender } = render(
      <Pagination currentPage={1} totalPages={5} onPageChange={vi.fn()} density="full" />,
    );
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled();

    rerender(<Pagination currentPage={5} totalPages={5} onPageChange={vi.fn()} density="full" />);
    expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled();
  });

  it('renders the full control set including first and last page on desktop density', () => {
    render(<Pagination currentPage={10} totalPages={20} onPageChange={vi.fn()} density="full" />);

    const nav = screen.getByRole('navigation', { name: '分页导航' });
    expect(nav).toHaveAttribute('data-pagination-density', 'full');
    // Full density: ±2 window with first/last (ellipsis spans are not buttons).
    expect(pageNumberLabels(nav)).toEqual(['1', '8', '9', '10', '11', '12', '20']);
    expect(screen.getByRole('button', { name: '1' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '20' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '上一页' })).toHaveAttribute('aria-label', '上一页');
    expect(screen.getByRole('button', { name: '下一页' })).toHaveAttribute('aria-label', '下一页');
  });

  it('renders the compact control set (prev / x / y / next) with first and last reachable', () => {
    const onPageChange = vi.fn();
    const { unmount: unmountMiddle } = render(
      <Pagination currentPage={10} totalPages={20} onPageChange={onPageChange} density="compact" />,
    );

    const nav = screen.getByRole('navigation', { name: '分页导航' });
    expect(nav).toHaveAttribute('data-pagination-density', 'compact');
    // Compact: current + last only (prev/next flank them).
    expect(pageNumberLabels(nav)).toEqual(['10', '20']);
    expect(screen.getByRole('button', { name: '上一页' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '下一页' })).toBeEnabled();
    // Last page is a direct control; first is reachable via prev (or when on last page).
    expect(screen.getByRole('button', { name: '20' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '1' })).not.toBeInTheDocument();
    unmountMiddle();

    // On the last page, first becomes a direct control.
    render(
      <Pagination currentPage={20} totalPages={20} onPageChange={onPageChange} density="compact" />,
    );
    const lastNav = screen.getByRole('navigation', { name: '分页导航' });
    expect(pageNumberLabels(lastNav)).toEqual(['1', '20']);
    expect(within(lastNav).getByRole('button', { name: '1' })).toBeInTheDocument();
    expect(within(lastNav).getByRole('button', { name: '20' })).toHaveAttribute('aria-current', 'page');
  });

  it('compacts first-page control set to first + last', () => {
    render(<Pagination currentPage={1} totalPages={20} onPageChange={vi.fn()} density="compact" />);
    const nav = screen.getByRole('navigation', { name: '分页导航' });
    expect(pageNumberLabels(nav)).toEqual(['1', '20']);
  });

  it('preserves prev/next aria-labels in compact density', () => {
    render(<Pagination currentPage={3} totalPages={12} onPageChange={vi.fn()} density="compact" />);

    expect(screen.getByRole('navigation', { name: '分页导航' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '上一页' })).toHaveAttribute('aria-label', '上一页');
    expect(screen.getByRole('button', { name: '下一页' })).toHaveAttribute('aria-label', '下一页');
  });

  it('allows horizontal overflow instead of clipping controls', () => {
    render(<Pagination currentPage={10} totalPages={20} onPageChange={vi.fn()} density="full" />);

    const nav = screen.getByRole('navigation', { name: '分页导航' });
    expect(nav).toHaveClass('max-w-full');
    expect(nav).toHaveClass('overflow-x-auto');
    expect(nav).not.toHaveClass('overflow-hidden');
  });
});
