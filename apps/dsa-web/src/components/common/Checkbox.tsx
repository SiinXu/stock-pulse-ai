import type React from 'react';
import { forwardRef, useId } from 'react';
import { cn } from '../../utils/cn';

export interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: React.ReactNode;
  containerClassName?: string;
}

/**
 * Shared checkbox matching the 24px Figma control and preserving native input semantics.
 */
export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(({
  label,
  id,
  className = '',
  containerClassName = '',
  ...props
}, ref) => {
  const generatedId = useId();
  const checkboxId = id ?? generatedId;

  return (
    <label
      htmlFor={checkboxId}
      className={cn(
        'flex items-center gap-2 select-none',
        props.disabled ? 'cursor-not-allowed' : 'cursor-pointer',
        containerClassName,
        'min-h-11 min-w-11',
      )}
    >
      <span className="relative h-6 w-6 shrink-0">
        <input
          ref={ref}
          id={checkboxId}
          type="checkbox"
          className={cn(
            'shared-checkbox-input absolute inset-0 z-10 h-6 w-6 cursor-pointer appearance-none opacity-0',
            'focus:outline-none disabled:cursor-not-allowed',
            className
          )}
          {...props}
        />
        <span className="shared-checkbox-control absolute inset-0.5" aria-hidden="true" />
      </span>
      {label ? <span className="text-sm font-medium text-foreground">{label}</span> : null}
    </label>
  );
});

Checkbox.displayName = 'Checkbox';
