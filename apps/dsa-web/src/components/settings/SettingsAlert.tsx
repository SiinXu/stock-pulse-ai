import type React from 'react';
import { Button, InlineAlert } from '../common';
import { cn } from '../../utils/cn';

interface SettingsAlertProps {
  title: string;
  message: string;
  variant?: 'error' | 'success' | 'warning';
  presentation?: 'inline' | 'toast';
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

const variantMap: Record<NonNullable<SettingsAlertProps['variant']>, 'danger' | 'success' | 'warning'> = {
  error: 'danger',
  success: 'success',
  warning: 'warning',
};

const toastHighlightStyle = [
  'relative overflow-hidden bg-card/95 text-foreground shadow-soft-card-strong backdrop-blur-sm',
  'before:pointer-events-none before:absolute before:inset-x-0 before:top-0 before:h-1.5',
  'before:bg-gradient-to-r before:from-primary/70 before:via-primary/40 before:to-transparent',
].join(' ');

const toastVariantStyles: Record<NonNullable<SettingsAlertProps['variant']>, string> = {
  error: toastHighlightStyle,
  success: toastHighlightStyle,
  warning: toastHighlightStyle,
};

export const SettingsAlert: React.FC<SettingsAlertProps> = ({
  title,
  message,
  variant = 'error',
  presentation = 'inline',
  actionLabel,
  onAction,
  className = '',
}) => {
  const presentationClassName = presentation === 'toast' ? toastVariantStyles[variant] : '';

  return (
    <InlineAlert
      title={title}
      message={message}
      variant={variantMap[variant]}
      className={cn(presentationClassName, className)}
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
