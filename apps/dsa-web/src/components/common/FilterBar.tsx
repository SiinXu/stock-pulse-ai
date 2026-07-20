// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { ListFilter } from 'lucide-react';
import {
  forwardRef,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from 'react';
import { cn } from '../../utils/cn';
import { Button } from './Button';

export interface FilterBarProps extends Omit<
  ComponentPropsWithoutRef<'form'>,
  'children' | 'onSubmit'
> {
  children: ReactNode;
  advanced?: ReactNode;
  applied?: ReactNode;
  applyLabel: string;
  loadingLabel?: string;
  onApply: () => void;
  applyDisabled?: boolean;
  isApplying?: boolean;
}

/** Compact primary-filter form with separate advanced and applied-filter slots. */
export const FilterBar = forwardRef<HTMLFormElement, FilterBarProps>(({
  children,
  advanced,
  applied,
  applyLabel,
  loadingLabel,
  onApply,
  applyDisabled = false,
  isApplying = false,
  className,
  ...formProps
}, ref) => {
  const applyBlocked = applyDisabled || isApplying;

  return (
    <div className="space-y-3" data-filter-pattern="bar">
      <form
        {...formProps}
        ref={ref}
        className={cn(
          'flex min-w-0 flex-col gap-3 lg:flex-row lg:items-end',
          className,
        )}
        onSubmit={(event) => {
          event.preventDefault();
          if (applyBlocked) return;
          onApply();
        }}
      >
        <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-2" data-filter-slot="primary">
          {children}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2" data-filter-slot="actions">
          {advanced}
          <Button
            type="submit"
            variant="secondary"
            size="comfortable"
            disabled={applyBlocked}
            isLoading={isApplying}
            loadingText={loadingLabel}
          >
            <ListFilter aria-hidden="true" />
            {applyLabel}
          </Button>
        </div>
      </form>
      {applied}
    </div>
  );
});

FilterBar.displayName = 'FilterBar';
