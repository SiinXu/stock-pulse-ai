import type React from 'react';
import { cn } from '../../utils/cn';
import { Surface } from './Surface';

interface CardProps {
  title?: string;
  subtitle?: string;
  /** Optional content aligned to the right of the header (e.g. a scope badge). */
  headerRight?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  variant?: 'default' | 'bordered' | 'gradient';
  hoverable?: boolean;
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

/**
 * Card component with terminal-inspired variants and optional hover styling.
 */
export const Card: React.FC<CardProps> = ({
  title,
  subtitle,
  headerRight,
  children,
  className = '',
  style,
  variant = 'default',
  hoverable = false,
  padding = 'md',
}) => {
  const header = (title || subtitle || headerRight) ? (
    <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        {subtitle ? <span className="label-uppercase">{subtitle}</span> : null}
        {title ? <h3 className="mt-1 text-lg font-semibold text-foreground">{title}</h3> : null}
      </div>
      {headerRight ? <div className="min-w-0 max-w-full shrink-0">{headerRight}</div> : null}
    </div>
  ) : null;
  const paddingStyles = {
    none: '',
    sm: 'p-4',
    md: 'p-5',
    lg: 'p-6',
  };

  const hoverStyles = hoverable ? 'cursor-pointer transition-[border-color,box-shadow] hover:border-subtle-hover hover:shadow-soft-card-strong' : '';

  if (variant === 'gradient') {
    return (
      <div className={cn('gradient-border-card', className)} style={style}>
        <div className={cn('gradient-border-card-inner', paddingStyles[padding])}>
          {header}
          {children}
        </div>
      </div>
    );
  }

  return (
    <Surface
      variant={variant === 'default' ? 'elevated' : 'bordered'}
      radius="lg"
      padding="none"
      style={style}
      className={cn(
        'overflow-hidden',
        variant === 'default' && 'terminal-card',
        hoverStyles,
        paddingStyles[padding],
        className,
      )}
    >
      {header}
      {children}
    </Surface>
  );
};
