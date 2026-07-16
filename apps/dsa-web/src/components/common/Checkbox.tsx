import type React from 'react';
import { useId } from 'react';
import { cn } from '../../utils/cn';

interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string;
  containerClassName?: string;
}

/**
 * Compact visual checkbox with a 44px interactive target.
 */
export const Checkbox: React.FC<CheckboxProps> = ({
  label,
  id,
  className = '',
  containerClassName = '',
  ...props
}) => {
  const generatedId = useId();
  const checkboxId = id ?? generatedId;

  return (
    <label
      htmlFor={checkboxId}
      className={cn(
        'flex min-h-11 min-w-11 items-center gap-3 select-none',
        props.disabled ? 'cursor-not-allowed' : 'cursor-pointer',
        containerClassName
      )}
    >
      <input
        id={checkboxId}
        type="checkbox"
        className={cn(
          'h-4 w-4 cursor-pointer rounded border border-border/70 bg-base text-cyan transition-all',
          'focus:ring-2 focus:ring-cyan/20 focus:outline-none',
          'disabled:cursor-not-allowed disabled:opacity-50',
          className
        )}
        {...props}
      />
      {label ? <span className="text-sm font-medium text-foreground">{label}</span> : null}
    </label>
  );
};
