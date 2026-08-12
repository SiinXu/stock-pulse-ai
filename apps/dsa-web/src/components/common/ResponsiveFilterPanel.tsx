// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useEffect, useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { cn } from '../../utils/cn';
import { Badge } from './Badge';
import { Button } from './Button';
import { Drawer } from './Drawer';

/**
 * Below Tailwind `lg` (64rem). Prefer max-width so jsdom/setupTests matchMedia
 * stubs that always return `matches: false` keep the desktop inline layout
 * (filter interaction tests assume reachable basic fields without opening a drawer).
 */
const MOBILE_FILTER_QUERY = '(max-width: 63.99875rem)';

function isMobileFilterViewport(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(MOBILE_FILTER_QUERY).matches;
}

export interface ResponsiveFilterPanelProps {
  basic: React.ReactNode;
  advanced: React.ReactNode;
  filterLabel: string;
  drawerTitle: string;
  applyLabel: string;
  onApply: () => void;
  applyDisabled?: boolean;
  isApplying?: boolean;
  loadingLabel?: string;
  activeCount?: number;
  resetLabel?: string;
  onReset?: () => void;
  className?: string;
  basicClassName?: string;
  advancedClassName?: string;
  drawerAdvancedClassName?: string;
}

export const ResponsiveFilterPanel: React.FC<ResponsiveFilterPanelProps> = ({
  basic,
  advanced,
  filterLabel,
  drawerTitle,
  applyLabel,
  onApply,
  applyDisabled = false,
  isApplying = false,
  loadingLabel,
  activeCount = 0,
  resetLabel,
  onReset,
  className,
  basicClassName,
  advancedClassName,
  drawerAdvancedClassName,
}) => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(isMobileFilterViewport);
  const applyBlocked = applyDisabled || isApplying;

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const media = window.matchMedia(MOBILE_FILTER_QUERY);
    const update = () => {
      setIsMobile(media.matches);
      // Close the mobile drawer when leaving the narrow layout so focus is not trapped.
      setMobileOpen(false);
    };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  const applyMobileFilters = () => {
    if (applyBlocked) return;
    onApply();
    setMobileOpen(false);
  };

  return (
    <>
      <form
        className={cn('min-w-0 space-y-3', className)}
        onSubmit={(event) => {
          event.preventDefault();
          if (!applyBlocked) onApply();
        }}
      >
        {isMobile ? (
          // #879 B2: mobile first screen shows a single Filters control, not the basic row.
          <div className="flex justify-end">
            <Button
              type="button"
              variant="secondary"
              size="comfortable"
              aria-label={`${filterLabel} (${activeCount})`}
              aria-expanded={mobileOpen}
              onClick={() => setMobileOpen(true)}
            >
              <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
              <span aria-hidden="true">{filterLabel}</span>
              {activeCount > 0 ? <Badge size="sm">{activeCount}</Badge> : null}
            </Button>
          </div>
        ) : (
          <>
            <div className={cn('grid min-w-0 items-end gap-2', basicClassName)}>{basic}</div>
            <div className="flex min-w-0 items-end gap-2">
              <div className={cn('grid min-w-0 flex-1 items-end gap-2', advancedClassName)}>{advanced}</div>
              {onReset && resetLabel ? (
                <Button type="button" variant="ghost" size="comfortable" onClick={onReset}>
                  {resetLabel}
                </Button>
              ) : null}
              <Button
                type="submit"
                variant="primary"
                size="comfortable"
                disabled={applyBlocked}
                isLoading={isApplying}
                loadingText={loadingLabel}
              >
                {applyLabel}
              </Button>
            </div>
          </>
        )}
      </form>

      {isMobile ? (
        <Drawer
          isOpen={mobileOpen}
          onClose={() => setMobileOpen(false)}
          title={drawerTitle}
          variant="detail"
          size="default"
          closeDisabled={isApplying}
          footer={(
            <>
              {onReset && resetLabel ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="comfortable"
                  disabled={isApplying}
                  onClick={onReset}
                >
                  {resetLabel}
                </Button>
              ) : null}
              <Button
                type="button"
                variant="primary"
                size="comfortable"
                disabled={applyBlocked}
                isLoading={isApplying}
                loadingText={loadingLabel}
                onClick={applyMobileFilters}
              >
                {applyLabel}
              </Button>
            </>
          )}
        >
          <div className="space-y-4">
            <div className={cn('grid items-end gap-3', basicClassName)}>{basic}</div>
            <div className={cn('grid items-end gap-3', drawerAdvancedClassName)}>{advanced}</div>
          </div>
        </Drawer>
      ) : null}
    </>
  );
};
