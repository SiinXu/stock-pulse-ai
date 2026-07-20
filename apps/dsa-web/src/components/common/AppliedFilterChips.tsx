// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { X } from 'lucide-react';
import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cn } from '../../utils/cn';
import { Button } from './Button';

export interface FilterChipProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  'aria-label' | 'children' | 'className' | 'type'
> {
  label: string;
  value: string;
  removeLabel: string;
}

/** Applied-filter token; activating it removes that exact filter. */
export const FilterChip = forwardRef<HTMLButtonElement, FilterChipProps>(({
  label,
  value,
  removeLabel,
  ...buttonProps
}, ref) => (
  <button
    {...buttonProps}
    ref={ref}
    type="button"
    aria-label={removeLabel}
    data-control="filter-chip"
    className="control-hit-target relative inline-flex h-7 max-w-full items-center gap-1.5 rounded-full border border-border bg-elevated px-2.5 text-xs text-secondary-text transition-colors hover:border-primary/45 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/55 focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50"
  >
    <span className="truncate">
      <span className="font-medium text-foreground">{label}</span>
      <span aria-hidden="true">: </span>
      {value}
    </span>
    <X className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
  </button>
));

FilterChip.displayName = 'FilterChip';

export interface AppliedFilterItem {
  id: string;
  label: string;
  value: string;
  removeLabel: string;
  onRemove: () => void;
  disabled?: boolean;
}

export interface AppliedFilterChipsProps {
  'aria-label': string;
  filters: readonly AppliedFilterItem[];
  clearAllLabel: string;
  onClearAll: () => void;
  disabled?: boolean;
  className?: string;
}

/** Applied-filter summary with per-filter removal and one explicit reset. */
export const AppliedFilterChips = ({
  'aria-label': ariaLabel,
  filters,
  clearAllLabel,
  onClearAll,
  disabled = false,
  className,
}: AppliedFilterChipsProps) => {
  if (filters.length === 0) return null;

  return (
    <div className={cn('flex min-w-0 flex-wrap items-center gap-2', className)}>
      <div className="flex min-w-0 flex-wrap items-center gap-2" role="list" aria-label={ariaLabel}>
        {filters.map((filter) => (
          <span key={filter.id} role="listitem" className="min-w-0">
            <FilterChip
              label={filter.label}
              value={filter.value}
              removeLabel={filter.removeLabel}
              disabled={disabled || filter.disabled}
              onClick={filter.onRemove}
            />
          </span>
        ))}
      </div>
      <Button
        type="button"
        variant="ghost"
        size="compact"
        disabled={disabled}
        onClick={onClearAll}
      >
        {clearAllLabel}
      </Button>
    </div>
  );
};
