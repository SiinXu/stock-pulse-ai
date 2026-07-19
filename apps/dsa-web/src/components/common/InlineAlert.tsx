import type React from 'react';
import { forwardRef } from 'react';
import { Alert, type AlertSize, type AlertTone } from './Alert';

export type InlineAlertVariant = 'info' | 'success' | 'warning' | 'danger';

export interface InlineAlertProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title' | 'role' | 'aria-live'> {
  title?: string;
  message: React.ReactNode;
  variant?: InlineAlertVariant;
  size?: AlertSize;
  action?: React.ReactNode;
  urgent?: boolean;
}

export const InlineAlert = forwardRef<HTMLDivElement, InlineAlertProps>(({
  title,
  message,
  variant = 'info',
  size = 'default',
  action,
  className = '',
  urgent = false,
  ...props
}, ref) => (
  <Alert
    {...props}
    ref={ref}
    tone={variant as AlertTone}
    size={size}
    title={title}
    action={action}
    urgent={urgent}
    className={className}
  >
    {message}
  </Alert>
));

InlineAlert.displayName = 'InlineAlert';
