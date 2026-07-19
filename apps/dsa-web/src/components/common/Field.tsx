import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export interface FieldProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'children'> {
  controlId: string;
  label?: React.ReactNode;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  children: React.ReactNode;
  labelClassName?: string;
  hintClassName?: string;
  errorClassName?: string;
  hintId?: string;
  errorId?: string;
}

export const Field = forwardRef<HTMLDivElement, FieldProps>(({
  controlId,
  label,
  hint,
  error,
  children,
  className,
  labelClassName,
  hintClassName,
  errorClassName,
  hintId,
  errorId,
  ...props
}, ref) => (
  <div {...props} ref={ref} className={cn('flex flex-col', className)}>
    {label ? (
      <label
        htmlFor={controlId}
        className={cn('mb-1.5 text-xs font-medium text-secondary-text', labelClassName)}
      >
        {label}
      </label>
    ) : null}
    {children}
    {error ? (
      <p id={errorId} role="alert" className={cn('mt-2 text-xs text-danger', errorClassName)}>
        {error}
      </p>
    ) : hint ? (
      <p id={hintId} className={cn('mt-2 text-xs text-secondary-text', hintClassName)}>
        {hint}
      </p>
    ) : null}
  </div>
));

Field.displayName = 'Field';
