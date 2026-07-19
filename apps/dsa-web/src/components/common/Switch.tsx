// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export interface SwitchProps extends Omit<
  React.ButtonHTMLAttributes<HTMLButtonElement>,
  'aria-checked' | 'onChange' | 'onClick' | 'role'
> {
  checked: boolean;
  onCheckedChange: (next: boolean) => void;
  testId?: string;
  visualTestId?: string;
}

export const Switch = forwardRef<HTMLButtonElement, SwitchProps>(({
  checked,
  onCheckedChange,
  id,
  disabled = false,
  testId,
  visualTestId,
  className,
  type = 'button',
  ...props
}, ref) => (
  <button
    {...props}
    ref={ref}
    id={id}
    type={type}
    role="switch"
    aria-checked={checked}
    disabled={disabled}
    data-testid={testId}
    data-state={checked ? 'checked' : 'unchecked'}
    onClick={() => onCheckedChange(!checked)}
    className={cn(
      'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg transition-colors',
      'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-foreground/15',
      disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
      className,
    )}
  >
    <span
      className={cn(
        'relative inline-flex h-6 w-10 shrink-0 items-center rounded-full transition-colors',
        checked
          ? 'bg-[linear-gradient(211deg,rgb(var(--switch-track-on-start))_0%,rgb(var(--switch-track-on-end))_100%)]'
          : 'bg-[rgb(var(--switch-track-off))]',
      )}
      data-testid={visualTestId}
      aria-hidden="true"
    >
      <span
        className={cn(
          'inline-block h-5 w-5 rounded-full bg-[rgb(var(--switch-thumb))] shadow-sm transition-transform',
          checked ? 'translate-x-4' : 'translate-x-0.5',
        )}
      />
    </span>
  </button>
));

Switch.displayName = 'Switch';
