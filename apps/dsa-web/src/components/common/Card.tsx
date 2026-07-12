import type React from 'react';
import { cn } from '../../utils/cn';

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
    <div className="mb-3 flex items-start justify-between gap-3">
      <div className="min-w-0">
        {subtitle ? <span className="label-uppercase">{subtitle}</span> : null}
        {title ? <h3 className="mt-1 text-lg font-semibold text-foreground">{title}</h3> : null}
      </div>
      {headerRight ? <div className="shrink-0">{headerRight}</div> : null}
    </div>
  ) : null;
  const paddingStyles = {
    none: '',
    sm: 'p-4',
    md: 'p-5',
    lg: 'p-6',
  };

  const variantStyles = {
    default: 'terminal-card',
    bordered: 'terminal-card',
    gradient: 'gradient-border-card',
  };

  const hoverStyles = hoverable ? 'terminal-card-hover cursor-pointer' : '';

  if (variant === 'gradient') {
    return (
      <div className={cn(variantStyles.gradient, className)} style={style}>
        <div className={cn('gradient-border-card-inner', paddingStyles[padding])}>
          {header}
          {children}
        </div>
      </div>
    );
  }

  return (
    <div
      style={style}
      className={cn('rounded-2xl', variantStyles[variant], hoverStyles, paddingStyles[padding], className)}
    >
      {header}
      {children}
    </div>
  );
};
