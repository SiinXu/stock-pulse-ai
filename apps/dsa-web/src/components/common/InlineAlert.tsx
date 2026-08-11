import type React from 'react';
import { forwardRef } from 'react';
import { Alert, type AlertSize, type AlertTone } from './Alert';

export type InlineAlertVariant = 'info' | 'success' | 'warning' | 'danger';

type InlineAlertBaseProps = Omit<React.HTMLAttributes<HTMLDivElement>, 'title' | 'role' | 'aria-live'> & {
  title?: string;
  message: React.ReactNode;
  variant?: InlineAlertVariant;
  size?: AlertSize;
  action?: React.ReactNode;
  urgent?: boolean;
};

type DismissibleInlineAlertProps = {
  dismissLabel: string;
  onDismiss: () => void;
} | {
  dismissLabel?: never;
  onDismiss?: never;
};

export type InlineAlertProps = InlineAlertBaseProps & DismissibleInlineAlertProps;

export const InlineAlert = forwardRef<HTMLDivElement, InlineAlertProps>(({
  title,
  message,
  variant = 'info',
  size = 'default',
  action,
  dismissLabel,
  onDismiss,
  className = '',
  urgent = false,
  ...props
}, ref) => {
  const sharedProps = {
    ...props,
    ref,
    tone: variant as AlertTone,
    size,
    title,
    action,
    urgent,
    className,
  };
  if (dismissLabel && onDismiss) {
    return (
      <Alert {...sharedProps} dismissLabel={dismissLabel} onDismiss={onDismiss}>
        {message}
      </Alert>
    );
  }
  return <Alert {...sharedProps}>{message}</Alert>;
});

InlineAlert.displayName = 'InlineAlert';
