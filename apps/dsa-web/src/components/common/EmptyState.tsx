import type React from 'react';
import { forwardRef } from 'react';
import { StatePanel } from './StatePanel';

export interface EmptyStateProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  compact?: boolean;
}

export const EmptyState = forwardRef<HTMLElement, EmptyStateProps>(({
  title,
  description,
  icon,
  action,
  className = '',
  compact = false,
  ...props
}, ref) => (
  <StatePanel
    {...props}
    ref={ref}
    state="empty"
    title={title}
    titleAs="h3"
    description={description}
    icon={icon}
    action={action}
    size={compact ? 'compact' : 'default'}
    className={className}
  />
));

EmptyState.displayName = 'EmptyState';
