import type React from 'react';
import { forwardRef } from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';

export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger' | 'danger-subtle';
export type ButtonSize = 'compact' | 'default' | 'comfortable' | 'primary';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  /** Custom loading text. */
  loadingText?: string;
  glow?: boolean;
}

const BUTTON_SIZE_STYLES = {
  compact: 'h-5 min-w-5 rounded-md px-2 text-xs',
  default: 'h-6 min-w-6 rounded-md px-2.5 text-xs',
  comfortable: 'h-7 min-w-7 rounded-md px-3 text-sm',
  primary: 'h-8 min-w-8 rounded-lg px-3.5 text-sm',
} as const;

const PRIMARY_BUTTON_STYLES = 'border border-transparent bg-foreground text-background shadow-soft-card hover:brightness-110';

const BUTTON_VARIANT_STYLES = {
  primary: PRIMARY_BUTTON_STYLES,
  secondary: 'border border-border bg-hover text-foreground shadow-soft-card hover:bg-subtle-hover dark:bg-border dark:hover:bg-subtle-active',
  outline: 'border border-border bg-transparent text-foreground hover:bg-hover',
  ghost: 'border border-transparent bg-transparent text-secondary-text hover:bg-hover hover:text-foreground',
  danger: 'border border-transparent bg-danger text-destructive-foreground shadow-soft-card hover:brightness-105',
  'danger-subtle': 'border border-danger/50 bg-danger/10 text-danger hover:bg-danger/15',
} as const;

/**
 * Button component with multiple variants and terminal-inspired styling.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({
  children,
  variant,
  size = 'comfortable',
  isLoading = false,
  loadingText,
  glow = false,
  className = '',
  disabled,
  type = 'button',
  ...props
}, ref) => {
  const { t } = useUiLanguage();
  const emphasisStyles = glow ? 'shadow-soft-card hover:shadow-soft-card-strong' : '';

  return (
    <button
      {...props}
      ref={ref}
      type={type}
      aria-busy={isLoading || undefined}
      data-control="button"
      data-variant={variant}
      data-size={size}
      className={cn(
        'control-hit-target relative inline-flex cursor-pointer items-center justify-center gap-1.5 font-medium',
        'transition-[color,background-color,border-color,box-shadow,filter,opacity] duration-200 motion-reduce:transition-none',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25 focus-visible:ring-offset-0',
        'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 disabled:transform-none',
        BUTTON_SIZE_STYLES[size],
        BUTTON_VARIANT_STYLES[variant],
        emphasisStyles,
        className,
      )}
      disabled={disabled || isLoading}
    >
      {isLoading ? (
        <>
          <span className="sr-only">{children}</span>
          <span aria-hidden="true" className="flex items-center justify-center gap-2">
            <svg
              className="h-4 w-4 animate-spin text-current"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            {loadingText ?? t('common.processing')}
          </span>
        </>
      ) : (
        children
      )}
    </button>
  );
});

Button.displayName = 'Button';
