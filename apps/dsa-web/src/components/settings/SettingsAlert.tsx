import type React from 'react';
import { Button, InlineAlert } from '../common';

interface SettingsAlertProps {
  title: string;
  message: string;
  variant?: 'error' | 'success' | 'warning';
  actionLabel?: string;
  onAction?: () => void;
}

const variantMap: Record<NonNullable<SettingsAlertProps['variant']>, 'danger' | 'success' | 'warning'> = {
  error: 'danger',
  success: 'success',
  warning: 'warning',
};

export const SettingsAlert: React.FC<SettingsAlertProps> = ({
  title,
  message,
  variant = 'error',
  actionLabel,
  onAction,
}) => {
  return (
    <InlineAlert
      title={title}
      message={message}
      variant={variantMap[variant]}
      action={actionLabel && onAction ? (
        <Button
          type="button"
          variant="secondary"
          size="compact"
          onClick={onAction}
        >
          {actionLabel}
        </Button>
      ) : undefined}
    />
  );
};
