import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export interface SurfaceProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'plain' | 'subtle' | 'bordered' | 'elevated';
  radius?: 'none' | 'sm' | 'md' | 'lg';
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

const SURFACE_VARIANT_STYLES = {
  plain: 'bg-transparent',
  subtle: 'bg-card',
  bordered: 'border border-border bg-card',
  elevated: 'border border-border bg-card shadow-soft-card',
} as const;

const SURFACE_RADIUS_STYLES = {
  none: 'rounded-none',
  sm: 'rounded-md',
  md: 'rounded-lg',
  lg: 'rounded-xl',
} as const;

const SURFACE_PADDING_STYLES = {
  none: '',
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-5',
} as const;

export const Surface = forwardRef<HTMLDivElement, SurfaceProps>(({
  variant = 'plain',
  radius = 'none',
  padding = 'none',
  className,
  ...props
}, ref) => (
  <div
    ref={ref}
    className={cn(
      SURFACE_VARIANT_STYLES[variant],
      SURFACE_RADIUS_STYLES[radius],
      SURFACE_PADDING_STYLES[padding],
      className,
    )}
    {...props}
  />
));

Surface.displayName = 'Surface';
