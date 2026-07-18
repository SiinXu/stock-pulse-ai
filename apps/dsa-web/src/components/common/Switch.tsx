// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { cn } from '../../utils/cn';

export interface SwitchProps {
  checked: boolean;
  onCheckedChange: (next: boolean) => void;
  id?: string;
  disabled?: boolean;
  testId?: string;
  visualTestId?: string;
  'aria-label'?: string;
  'aria-invalid'?: boolean;
  'aria-describedby'?: string;
}

export const Switch: React.FC<SwitchProps> = ({
  checked,
  onCheckedChange,
  id,
  disabled = false,
  testId,
  visualTestId,
  'aria-label': ariaLabel,
  'aria-invalid': ariaInvalid,
  'aria-describedby': ariaDescribedBy,
}) => (
  <button
    id={id}
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={ariaLabel}
    aria-invalid={ariaInvalid || undefined}
    aria-describedby={ariaDescribedBy}
    disabled={disabled}
    data-testid={testId}
    onClick={() => onCheckedChange(!checked)}
    className={cn(
      'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg transition-colors',
      disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
    )}
  >
    <span
      className={cn(
        'relative inline-flex h-6 w-10 shrink-0 items-center rounded-full transition-colors',
        checked
          ? 'bg-[linear-gradient(211deg,rgb(var(--settings-switch-on-start))_0%,rgb(var(--settings-switch-on-end))_100%)]'
          : 'bg-[rgb(var(--settings-switch-off))]',
      )}
      data-testid={visualTestId}
      aria-hidden="true"
    >
      <span
        className={cn(
          'inline-block h-5 w-5 rounded-full bg-white transition-transform',
          checked ? 'translate-x-4' : 'translate-x-0.5',
        )}
      />
    </span>
  </button>
);
