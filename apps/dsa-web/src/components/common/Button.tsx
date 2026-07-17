import React from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'gradient' | 'danger' | 'danger-subtle' | 'settings-primary' | 'settings-secondary' | 'action-primary' | 'action-secondary' | 'home-action-ai' | 'home-action-report';
  size?: 'xsm' | 'sm' | 'md' | 'lg' | 'xl' | 'icon';
  isLoading?: boolean;
  /** Custom loading text. */
  loadingText?: string;
  glow?: boolean;
}

const BUTTON_SIZE_STYLES = {
  xsm: 'h-6 min-h-11 min-w-11 rounded-full px-2.5 text-xs',
  sm: 'h-8 min-h-11 min-w-11 rounded-full px-3.5 text-xs',
  md: 'h-9 min-h-11 min-w-11 rounded-full px-4 text-sm',
  lg: 'h-10 min-h-11 min-w-11 rounded-full px-5 text-sm',
  xl: 'h-11 min-h-11 min-w-11 rounded-full px-6 text-sm',
  icon: 'h-11 min-h-11 w-11 min-w-11 shrink-0 rounded-full p-0 text-sm',
} as const;

const ACTION_AI_STYLES = 'bg-[var(--home-action-ai-bg)] border border-[var(--home-action-ai-border)] text-[var(--home-action-ai-text)] hover:bg-[var(--home-action-ai-hover-bg)]';
const ACTION_REPORT_STYLES = 'bg-[var(--home-action-report-bg)] border border-[var(--home-action-report-border)] text-[var(--home-action-report-text)] hover:bg-[var(--home-action-report-hover-bg)]';
const PRIMARY_BUTTON_STYLES = 'border border-transparent bg-foreground text-background shadow-soft-card hover:brightness-110';

const BUTTON_VARIANT_STYLES = {
  primary: PRIMARY_BUTTON_STYLES,
  secondary: 'border border-border bg-card text-foreground shadow-soft-card hover:bg-hover',
  'settings-primary': PRIMARY_BUTTON_STYLES,
  'settings-secondary': 'border settings-button-secondary hover:translate-y-[-1px]',
  outline: 'border border-border bg-transparent text-foreground hover:bg-hover',
  ghost: 'border border-transparent bg-transparent text-secondary-text hover:bg-hover hover:text-foreground',
  gradient: PRIMARY_BUTTON_STYLES,
  danger: 'border border-transparent bg-danger text-destructive-foreground shadow-soft-card hover:brightness-105',
  'danger-subtle': 'border border-danger/50 bg-danger/10 text-danger hover:bg-danger/15',
  'action-primary': ACTION_AI_STYLES,
  'action-secondary': ACTION_REPORT_STYLES,
  'home-action-ai': ACTION_AI_STYLES,
  'home-action-report': ACTION_REPORT_STYLES,
} as const;

/**
 * Button component with multiple variants and terminal-inspired styling.
 */
export const Button: React.FC<ButtonProps> = ({
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
}) => {
  const { t } = useUiLanguage();
  const emphasisStyles = glow ? 'shadow-soft-card hover:shadow-soft-card-strong' : '';

  return (
    <button
      type={type}
      aria-busy={isLoading || undefined}
      data-variant={variant}
      className={cn(
        'inline-flex cursor-pointer items-center justify-center gap-2 font-medium transition-all duration-200',
        'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25 focus-visible:ring-offset-0',
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
          <svg
            className="h-4 w-4 animate-spin text-current"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
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
          {size === 'icon' ? null : (loadingText ?? t('common.processing'))}
        </span>
      ) : (
        children
      )}
    </button>
  );
};
