import type React from 'react';
import { forwardRef } from 'react';
import { cn } from '../../utils/cn';
import { Surface, type SurfaceLevel } from './Surface';

export interface CardProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  title?: string;
  eyebrow?: React.ReactNode;
  description?: React.ReactNode;
  /** Optional content aligned to the right of the header (e.g. a scope badge). */
  headerRight?: React.ReactNode;
  children: React.ReactNode;
  level?: SurfaceLevel;
  hoverable?: boolean;
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

/**
 * Card composes the shared surface contract with an optional semantic header.
 */
export const Card = forwardRef<HTMLElement, CardProps>(({
  title,
  eyebrow,
  description,
  headerRight,
  children,
  className = '',
  style,
  level = 'section',
  hoverable = false,
  padding = 'md',
  ...props
}, ref) => {
  const header = (title || eyebrow || description || headerRight) ? (
    <div className="mb-3 flex items-start justify-between gap-3">
      <div className="min-w-0">
        {eyebrow ? <div className="label-uppercase">{eyebrow}</div> : null}
        {title ? <h3 className={cn('text-lg font-semibold text-foreground', eyebrow && 'mt-1')}>{title}</h3> : null}
        {description ? <div className="mt-1 text-sm text-secondary-text">{description}</div> : null}
      </div>
      {headerRight ? <div className="shrink-0">{headerRight}</div> : null}
    </div>
  ) : null;
  return (
    <Surface
      {...props}
      ref={ref}
      style={style}
      level={level}
      padding={padding}
      hoverable={hoverable}
      className={cn(hoverable && 'cursor-pointer', className)}
    >
      {header}
      {children}
    </Surface>
  );
});

Card.displayName = 'Card';
