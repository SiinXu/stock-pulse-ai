// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { Check } from 'lucide-react';
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { cn } from '../../utils/cn';

export interface SelectionChipProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  'aria-pressed' | 'children' | 'className' | 'style' | 'type'
> {
  label: ReactNode;
  description?: ReactNode;
  metadata?: ReactNode;
  /** Supply only when the selected state persists after activation. */
  selected?: boolean;
}

/** Compact text-led selection command whose visible surface may grow to multiple lines. */
export const SelectionChip = forwardRef<HTMLButtonElement, SelectionChipProps>(({
  label,
  description,
  metadata,
  selected,
  ...buttonProps
}, ref) => (
  <button
    {...buttonProps}
    ref={ref}
    type="button"
    aria-pressed={selected}
    data-control="selection-chip"
    data-selected={selected === undefined ? undefined : String(selected)}
    className={cn(
      'control-hit-target relative inline-flex min-h-9 min-w-0 max-w-full cursor-pointer items-center justify-center gap-2 rounded-lg border px-3 py-2 text-left text-sm font-medium leading-5 whitespace-normal',
      'transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-150 active:translate-y-px motion-reduce:transition-none motion-reduce:active:transform-none',
      'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25',
      'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 disabled:transform-none',
      selected
        ? 'border-primary/60 bg-primary/10 text-primary'
        : 'border-border bg-elevated/40 text-foreground hover:border-primary/45 hover:bg-hover hover:text-primary',
    )}
  >
    <span className="min-w-0 flex-1 break-words">
      <span>{label}</span>
      {description === undefined ? null : (
        <>
          {' '}
          <span className="text-secondary-text">{description}</span>
        </>
      )}
      {metadata === undefined ? null : (
        <>
          {' '}
          <span className="text-muted-text">{metadata}</span>
        </>
      )}
    </span>
    {selected === undefined ? null : (
      <span className="flex h-4 w-4 shrink-0 items-center justify-center" aria-hidden="true">
        <Check className={cn('h-3.5 w-3.5', selected ? 'opacity-100' : 'opacity-0')} />
      </span>
    )}
  </button>
));

SelectionChip.displayName = 'SelectionChip';
