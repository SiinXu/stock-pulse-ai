import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';
import { Spinner } from './Spinner';
import { Tooltip } from './Tooltip';

export interface IconButtonProps extends Omit<
  React.ButtonHTMLAttributes<HTMLButtonElement>,
  'aria-label' | 'children'
> {
  'aria-label': string;
  children: React.ReactNode;
  visualSize?: 'xs' | 'sm' | 'md' | 'lg';
  tone?: 'default' | 'danger';
  tooltip?: React.ReactNode | false;
  tooltipContentClassName?: string;
  visualClassName?: string;
  badge?: React.ReactNode;
  isLoading?: boolean;
}

const ICON_VISUAL_SIZE_STYLES = {
  xs: 'h-5 w-5',
  sm: 'h-6 w-6',
  md: 'h-7 w-7',
  lg: 'h-8 w-8',
} as const;

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(({
  children,
  visualSize = 'md',
  tone = 'default',
  tooltip,
  tooltipContentClassName,
  visualClassName,
  badge,
  isLoading = false,
  className,
  disabled,
  type = 'button',
  'aria-label': ariaLabel,
  ...props
}, ref) => {
  const button = (
    <button
      ref={ref}
      type={type}
      aria-label={ariaLabel}
      aria-busy={isLoading || undefined}
      disabled={disabled || isLoading}
      className={cn(
        'ui-touch-target group relative inline-flex shrink-0 items-center justify-center bg-transparent p-0',
        ICON_VISUAL_SIZE_STYLES[visualSize],
        'text-secondary-text transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/15',
        'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-40',
        tone === 'danger' ? 'hover:text-danger' : 'hover:text-foreground',
        className,
      )}
      {...props}
    >
      <span
        aria-hidden="true"
        className={cn(
          'pointer-events-none inline-flex items-center justify-center rounded-lg transition-colors group-hover:bg-hover',
          'group-aria-pressed:bg-hover group-aria-pressed:text-foreground',
          ICON_VISUAL_SIZE_STYLES[visualSize],
          visualClassName,
        )}
      >
        {isLoading ? <Spinner size="sm" /> : children}
      </span>
      {badge ? (
        <span className="pointer-events-none absolute right-0.5 top-0.5">{badge}</span>
      ) : null}
    </button>
  );

  const tooltipContent = tooltip === false ? null : (tooltip ?? ariaLabel);
  return tooltipContent ? (
    <Tooltip content={tooltipContent} contentClassName={tooltipContentClassName}>{button}</Tooltip>
  ) : button;
});

IconButton.displayName = 'IconButton';
