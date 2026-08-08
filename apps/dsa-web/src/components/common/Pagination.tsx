import type React from 'react';
import { useEffect, useRef, useState } from 'react';
import { cn } from '../../utils/cn';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

/** Containers narrower than this use the compact page set (prev / x / y / next). */
const PAGINATION_COMPACT_MAX_WIDTH_PX = 480;

interface PageButtonProps {
  page: number | string;
  isActive?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  ariaLabel?: string;
  children?: React.ReactNode;
}

const PageButton: React.FC<PageButtonProps> = ({ page, isActive, disabled, onClick, ariaLabel, children }) => {
  const isEllipsis = page === '...';

  if (isEllipsis) {
    return <span className="px-3 py-2 text-muted-text" aria-hidden="true">...</span>;
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      aria-current={isActive ? 'page' : undefined}
      className={cn(
        'inline-flex h-11 min-w-11 shrink-0 items-center justify-center rounded-lg border px-3 text-sm font-medium transition-all duration-200',
        isActive
          ? 'border-transparent bg-foreground text-background shadow-soft-card'
          : 'border-border bg-elevated text-secondary-text hover:bg-hover hover:text-foreground',
        disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
      )}
    >
      {children || page}
    </button>
  );
};

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
  /**
   * Density override. Defaults to `auto` (container-width driven).
   * Tests may pass `compact` or `full` to pin a density without ResizeObserver.
   */
  density?: 'auto' | 'compact' | 'full';
}

/**
 * Full density: first / last always visible, ±2 window around current (existing contract).
 * Compact density: at most two page numbers (current + last, or first + last on the ends)
 * so prev / x / y / next fits a 320px container with 44px touch targets.
 */
function buildPageNumbers(
  currentPage: number,
  totalPages: number,
  density: 'full' | 'compact',
): (number | string)[] {
  if (totalPages <= 1) return [];

  if (density === 'compact') {
    // 「上一页 / x / y / 下一页」: at most two page controls between prev and next.
    if (currentPage <= 1) {
      return currentPage === totalPages ? [1] : [1, totalPages];
    }
    if (currentPage >= totalPages) {
      return [1, totalPages];
    }
    // Middle: current + last (jump to end); first remains reachable via prev.
    return [currentPage, totalPages];
  }

  const pages: (number | string)[] = [];
  const delta = 2;

  for (let i = 1; i <= totalPages; i++) {
    if (
      i === 1
      || i === totalPages
      || (i >= currentPage - delta && i <= currentPage + delta)
    ) {
      pages.push(i);
    } else if (pages[pages.length - 1] !== '...') {
      pages.push('...');
    }
  }

  return pages;
}

/**
 * Pagination component with terminal-inspired styling.
 * Narrow containers collapse the page set; overflow never clips controls.
 */
export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  onPageChange,
  className = '',
  density = 'auto',
}) => {
  const { t } = useUiLanguage();
  const navRef = useRef<HTMLElement>(null);
  const [autoCompact, setAutoCompact] = useState(false);

  useEffect(() => {
    if (density !== 'auto') return undefined;
    const el = navRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;

    const update = (width: number) => {
      setAutoCompact(width > 0 && width < PAGINATION_COMPACT_MAX_WIDTH_PX);
    };

    update(el.getBoundingClientRect().width);

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      update(entry.contentRect.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [density]);

  if (totalPages <= 1) return null;

  const resolvedDensity: 'full' | 'compact' = density === 'auto'
    ? (autoCompact ? 'compact' : 'full')
    : density;
  const pageNumbers = buildPageNumbers(currentPage, totalPages, resolvedDensity);

  return (
    <nav
      ref={navRef}
      className={cn(
        // max-w-full + overflow-x-auto keep the strip scrollable when still tight after compact.
        // justify-center-safe: center when content fits; on overflow fall back to start alignment
        // so the leading control stays at scrollLeft 0 and remains reachable (unsafe center
        // would push the start half into clamped negative scroll space).
        'flex max-w-full items-center justify-center-safe gap-2 overflow-x-auto overscroll-x-contain',
        className,
      )}
      aria-label={t('common.pageNav')}
      data-pagination-density={resolvedDensity}
    >
      {/* Previous page */}
      <PageButton
        page="prev"
        disabled={currentPage === 1}
        onClick={() => onPageChange(currentPage - 1)}
        ariaLabel={t('common.prevPage')}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
      </PageButton>

      {/* Page numbers */}
      {pageNumbers.map((page, index) => (
        <PageButton
          key={`${page}-${index}`}
          page={page}
          isActive={page === currentPage}
          onClick={() => typeof page === 'number' && onPageChange(page)}
        />
      ))}

      {/* Next page */}
      <PageButton
        page="next"
        disabled={currentPage === totalPages}
        onClick={() => onPageChange(currentPage + 1)}
        ariaLabel={t('common.nextPage')}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </PageButton>
    </nav>
  );
};
