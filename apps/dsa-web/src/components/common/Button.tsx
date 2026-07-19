import type React from 'react';
import { forwardRef } from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { Spinner } from './Spinner';

export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'outline'
  | 'ghost'
  | 'danger'
  | 'danger-subtle';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: 'xsm' | 'sm' | 'md' | 'lg' | 'xl' | 'icon';
  isLoading?: boolean;
  /** Custom loading text. */
  loadingText?: string;
  glow?: boolean;
}

const BUTTON_SIZE_STYLES = {
  xsm: 'h-5 min-w-5 rounded-md px-2 text-xs',
  sm: 'h-6 min-w-6 rounded-md px-2.5 text-xs',
  md: 'h-7 min-w-7 rounded-md px-3 text-sm',
  lg: 'h-8 min-w-8 rounded-lg px-3.5 text-sm',
  xl: 'h-9 min-w-9 rounded-lg px-4 text-sm',
  icon: 'h-5 w-5 min-w-5 shrink-0 rounded-md p-0 text-sm',
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
  variant = 'primary',
  size = 'md',
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
      ref={ref}
      type={type}
      aria-busy={isLoading || undefined}
      data-variant={variant}
      className={cn(
        'ui-touch-target inline-flex cursor-pointer items-center justify-center gap-1.5 font-medium transition-all duration-200',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25 focus-visible:ring-offset-0',
        'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 disabled:transform-none',
        BUTTON_SIZE_STYLES[size],
        BUTTON_VARIANT_STYLES[variant],
        emphasisStyles,
        className,
      )}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <span className="flex items-center justify-center gap-2">
          <Spinner size="sm" />
          {size === 'icon' ? null : (loadingText ?? t('common.processing'))}
        </span>
      ) : (
        children
      )}
    </button>
  );
});

Button.displayName = 'Button';
