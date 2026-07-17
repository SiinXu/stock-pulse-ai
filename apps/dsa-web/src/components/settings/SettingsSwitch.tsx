import type React from 'react';
import { cn } from '../../utils/cn';

interface SettingsSwitchProps {
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

export const SettingsSwitch: React.FC<SettingsSwitchProps> = ({
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
      'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors',
      disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
    )}
  >
    <span
      className={cn(
        'relative inline-flex h-5 w-8 shrink-0 items-center rounded-full transition-colors',
        checked ? 'bg-foreground' : 'bg-border',
      )}
      data-testid={visualTestId}
      aria-hidden="true"
    >
      <span
        className={cn(
          'inline-block h-4 w-4 rounded-full bg-background shadow-sm transition-transform',
          checked ? 'translate-x-3' : 'translate-x-0.5',
        )}
      />
    </span>
  </button>
);
