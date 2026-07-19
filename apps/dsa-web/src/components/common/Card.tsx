import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';
import { Surface, type SurfaceLevel } from './Surface';

export interface CardProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  title?: string;
  subtitle?: string;
  /** Optional content aligned to the right of the header (e.g. a scope badge). */
  headerRight?: React.ReactNode;
  children: React.ReactNode;
  variant?: 'default' | 'bordered' | 'gradient';
  hoverable?: boolean;
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

/**
 * Card component with terminal-inspired variants and optional hover styling.
 */
export const Card = forwardRef<HTMLElement, CardProps>(({
  title,
  subtitle,
  headerRight,
  children,
  className = '',
  style,
  variant = 'default',
  hoverable = false,
  padding = 'md',
  ...props
}, ref) => {
  const header = (title || subtitle || headerRight) ? (
    <div className="mb-3 flex items-start justify-between gap-3">
      <div className="min-w-0">
        {subtitle ? <span className="label-uppercase">{subtitle}</span> : null}
        {title ? <h3 className="mt-1 text-lg font-semibold text-foreground">{title}</h3> : null}
      </div>
      {headerRight ? <div className="shrink-0">{headerRight}</div> : null}
    </div>
  ) : null;
  const level: SurfaceLevel = variant === 'default' ? 'section' : 'interactive';
  const legacyVariantClass = variant === 'bordered'
    ? 'terminal-card'
    : variant === 'gradient'
      ? 'gradient-border-card'
      : '';

  return (
    <Surface
      {...props}
      ref={ref}
      style={style}
      level={level}
      padding={padding}
      hoverable={hoverable}
      className={cn(legacyVariantClass, hoverable && 'terminal-card-hover cursor-pointer', className)}
    >
      {header}
      {children}
    </Surface>
  );
});

Card.displayName = 'Card';
