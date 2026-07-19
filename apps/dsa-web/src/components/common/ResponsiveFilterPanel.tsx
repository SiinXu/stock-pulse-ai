// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { cn } from '../../utils/cn';
import { Badge } from './Badge';
import { Button } from './Button';
import { Drawer } from './Drawer';

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

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onApply();
  };

  const handleMobileApply = () => {
    onApply();
    setMobileOpen(false);
  };

  return (
    <>
      <form className={cn('min-w-0 space-y-3', className)} onSubmit={handleSubmit}>
        <div className={cn('grid min-w-0 items-end gap-2', basicClassName)}>{basic}</div>
        {!mobileOpen ? (
          <div className="hidden min-w-0 items-end gap-2 lg:flex">
            <div className={cn('grid min-w-0 flex-1 items-end gap-2', advancedClassName)}>{advanced}</div>
            {onReset && resetLabel ? (
              <Button type="button" variant="ghost" size="md" onClick={onReset}>
                {resetLabel}
              </Button>
            ) : null}
            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={applyDisabled}
              isLoading={isApplying}
              loadingText={loadingLabel}
            >
              {applyLabel}
            </Button>
          </div>
        ) : null}
        <div className="flex justify-end lg:hidden">
          <Button
            type="button"
            variant="secondary"
            size="md"
            aria-label={`${filterLabel} (${activeCount})`}
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen(true)}
          >
            <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
            <span aria-hidden="true">{filterLabel}</span>
            {activeCount > 0 ? <Badge size="sm">{activeCount}</Badge> : null}
          </Button>
        </div>
      </form>

      <Drawer
        isOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
        title={drawerTitle}
        width="max-w-md"
        contentClassName="p-0"
      >
        <div className="flex min-h-full flex-col">
          <div className={cn('grid flex-1 items-end gap-3 p-5', drawerAdvancedClassName)}>
            {advanced}
          </div>
          <div className="sticky bottom-0 flex shrink-0 flex-wrap justify-end gap-2 border-t border-border bg-card px-5 py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
            {onReset && resetLabel ? (
              <Button type="button" variant="ghost" size="md" onClick={onReset}>
                {resetLabel}
              </Button>
            ) : null}
            <Button
              type="button"
              variant="primary"
              size="md"
              disabled={applyDisabled}
              isLoading={isApplying}
              loadingText={loadingLabel}
              onClick={handleMobileApply}
            >
              {applyLabel}
            </Button>
          </div>
        </div>
      </Drawer>
    </>
  );
};
