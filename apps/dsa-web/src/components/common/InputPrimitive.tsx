import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export interface InputPrimitiveProps extends React.InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

/** Low-level input used by Field-backed inputs and composite controls. */
export const InputPrimitive = forwardRef<HTMLInputElement, InputPrimitiveProps>(({
  invalid = false,
  className,
  ...props
}, ref) => (
  <input
    {...props}
    ref={ref}
    aria-invalid={props['aria-invalid'] ?? (invalid || undefined)}
    className={cn(
      'ui-touch-control h-9 min-h-9 min-w-9 w-full rounded-lg border border-border bg-transparent px-3 text-base text-foreground',
      'placeholder:text-muted-text transition-colors duration-200 focus:border-muted-text focus:outline-none sm:text-xs',
      'disabled:cursor-not-allowed disabled:opacity-60',
      invalid && 'border-danger/40 focus:border-danger',
      className,
    )}
  />
));

InputPrimitive.displayName = 'InputPrimitive';
