import type React from 'react';
import { forwardRef } from 'react';
import { X } from 'lucide-react';
import { cn } from '../../utils/cn';
import { IconButton } from './IconButton';

export type AlertTone = 'info' | 'success' | 'warning' | 'danger';
export type AlertSize = 'compact' | 'default';

type AlertBaseProps = Omit<React.HTMLAttributes<HTMLDivElement>, 'title' | 'children' | 'role' | 'aria-live'> & {
  tone?: AlertTone;
  size?: AlertSize;
  title?: React.ReactNode;
  children: React.ReactNode;
  action?: React.ReactNode;
  urgent?: boolean;
};

type DismissibleAlertProps = {
  dismissLabel: string;
  onDismiss: () => void;
} | {
  dismissLabel?: never;
  onDismiss?: never;
};

export type AlertProps = AlertBaseProps & DismissibleAlertProps;

const ALERT_TONE_STYLES: Record<AlertTone, string> = {
  info: 'border-border bg-surface-2/70 text-secondary-text',
  success: 'border-success/25 bg-success/10 text-success',
  warning: 'border-warning/25 bg-warning/10 text-warning',
  danger: 'border-danger/30 bg-danger/10 text-danger',
};

export const Alert = forwardRef<HTMLDivElement, AlertProps>(({
  tone = 'info',
  size = 'default',
  title,
  children,
  action,
  urgent = false,
  dismissLabel,
  onDismiss,
  className,
  ...props
}, ref) => {
  const role = tone === 'danger' || urgent ? 'alert' : 'status';
  const ariaLive = role === 'alert' ? 'assertive' : 'polite';

  return (
    <div
      {...props}
      ref={ref}
      role={role}
      aria-live={ariaLive}
      data-alert-tone={tone}
      data-alert-size={size}
      className={cn(
        'max-w-full overflow-hidden rounded-lg border',
        size === 'compact' ? 'px-3 py-2' : 'px-4 py-3',
        ALERT_TONE_STYLES[tone],
        className,
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          {title ? <div className="text-sm font-semibold">{title}</div> : null}
          <div className={cn('break-words text-sm [overflow-wrap:anywhere]', title && 'mt-1 opacity-90')}>
            {children}
          </div>
        </div>
        {action || onDismiss ? (
          <div className="flex shrink-0 items-center gap-2">
            {action}
            {onDismiss ? (
              <IconButton
                type="button"
                variant={tone === 'danger' ? 'danger' : 'ghost'}
                size="compact"
                aria-label={dismissLabel}
                onClick={onDismiss}
              >
                <X aria-hidden="true" />
              </IconButton>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
});

Alert.displayName = 'Alert';
