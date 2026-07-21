import type React from 'react';
import { forwardRef } from 'react';
import { LoaderCircle } from 'lucide-react';
import { cn } from '../../utils/cn';
import { Tooltip } from './Tooltip';

export type IconButtonSize = 'compact' | 'default' | 'comfortable' | 'navigation';
export type IconButtonVariant = 'ghost' | 'outline' | 'danger';

export interface IconButtonProps extends Omit<
  React.ButtonHTMLAttributes<HTMLButtonElement>,
  'aria-label' | 'children'
> {
  'aria-label': string;
  children: React.ReactNode;
  size?: IconButtonSize;
  variant?: IconButtonVariant;
  tooltip?: React.ReactNode | false;
  tooltipContentClassName?: string;
  isLoading?: boolean;
}

const ICON_BUTTON_SIZE_STYLES: Record<IconButtonSize, string> = {
  compact: 'h-7 w-7',
  default: 'h-8 w-8',
  comfortable: 'h-9 w-9',
  navigation: 'h-11 w-11',
};

const ICON_BUTTON_VARIANT_STYLES: Record<IconButtonVariant, string> = {
  ghost: 'border border-transparent bg-transparent text-secondary-text hover:bg-hover hover:text-foreground',
  outline: 'border border-border bg-transparent text-secondary-text hover:bg-hover hover:text-foreground',
  danger: 'border border-transparent bg-transparent text-danger hover:bg-danger/10',
};

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(({
  children,
  size = 'default',
  variant = 'ghost',
  tooltip,
  tooltipContentClassName,
  isLoading = false,
  className,
  disabled,
  type = 'button',
  'aria-label': ariaLabel,
  ...props
}, ref) => {
  const button = (
    <button
      {...props}
      ref={ref}
      type={type}
      aria-label={ariaLabel}
      aria-busy={isLoading || undefined}
      disabled={disabled || isLoading}
      data-control="icon-button"
      data-size={size}
      data-variant={variant}
      className={cn(
        'control-hit-target relative inline-flex shrink-0 items-center justify-center rounded-lg p-0',
        'transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-150 active:translate-y-px motion-reduce:transition-none motion-reduce:active:transform-none',
        'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25',
        'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
        '[&>svg]:h-4 [&>svg]:w-4',
        ICON_BUTTON_SIZE_STYLES[size],
        ICON_BUTTON_VARIANT_STYLES[variant],
        className,
      )}
    >
      {isLoading ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : children}
    </button>
  );

  const tooltipContent = tooltip === false ? null : (tooltip ?? ariaLabel);
  return tooltipContent ? (
    <Tooltip content={tooltipContent} contentClassName={tooltipContentClassName}>
      {button}
    </Tooltip>
  ) : button;
});

IconButton.displayName = 'IconButton';
