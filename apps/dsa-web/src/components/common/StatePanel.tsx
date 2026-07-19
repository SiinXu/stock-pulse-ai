// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { CheckCircle2, CircleAlert, Inbox, Info, LockKeyhole } from 'lucide-react';
import { cn } from '../../utils/cn';
import { Spinner } from './Spinner';

export type StatePanelStatus = 'loading' | 'empty' | 'error' | 'disabled' | 'partial' | 'ready';

export interface StatePanelProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  status: StatePanelStatus;
  title: React.ReactNode;
  description?: React.ReactNode;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  compact?: boolean;
  titleAs?: 'p' | 'h1' | 'h2' | 'h3' | 'h4' | 'span';
  titleClassName?: string;
  descriptionClassName?: string;
}

const DEFAULT_STATE_ICONS: Partial<Record<StatePanelStatus, React.ReactNode>> = {
  empty: <Inbox className="h-5 w-5" />,
  error: <CircleAlert className="h-5 w-5" />,
  disabled: <LockKeyhole className="h-5 w-5" />,
  partial: <Info className="h-5 w-5" />,
  ready: <CheckCircle2 className="h-5 w-5" />,
};

const STATE_ICON_STYLES: Record<StatePanelStatus, string> = {
  loading: 'bg-subtle text-secondary-text',
  empty: 'bg-subtle text-muted-text',
  error: 'bg-danger/10 text-danger',
  disabled: 'bg-subtle text-muted-text',
  partial: 'bg-warning/10 text-warning',
  ready: 'bg-success/10 text-success',
};

export const StatePanel: React.FC<StatePanelProps> = ({
  status,
  title,
  description,
  icon,
  action,
  compact = false,
  titleAs: Title = 'h3',
  titleClassName,
  descriptionClassName,
  className,
  role,
  ...props
}) => {
  const resolvedRole = role ?? (status === 'error' ? 'alert' : status === 'loading' ? 'status' : undefined);
  const resolvedIcon = status === 'loading'
    ? <Spinner size={compact ? 'md' : 'lg'} />
    : (icon ?? DEFAULT_STATE_ICONS[status]);

  return (
    <div
      role={resolvedRole}
      aria-busy={status === 'loading' || undefined}
      aria-live={status === 'loading' ? 'polite' : undefined}
      data-state={status}
      className={cn(
        'flex min-w-0 flex-col items-center justify-center text-center',
        compact ? 'gap-2 px-3 py-6' : 'min-h-40 gap-3 px-4 py-8',
        className,
      )}
      {...props}
    >
      {resolvedIcon ? (
        <div
          aria-hidden="true"
          className={cn(
            'flex shrink-0 items-center justify-center rounded-full',
            compact ? 'h-9 w-9' : 'h-11 w-11',
            STATE_ICON_STYLES[status],
          )}
        >
          {resolvedIcon}
        </div>
      ) : null}
      <div className="min-w-0 space-y-1">
        <Title className={cn('font-semibold text-foreground', compact ? 'text-sm' : 'text-base', titleClassName)}>
          {title}
        </Title>
        {description ? (
          <div className={cn('mx-auto max-w-md text-secondary-text', compact ? 'text-xs' : 'text-sm', descriptionClassName)}>
            {description}
          </div>
        ) : null}
      </div>
      {action ? <div className="flex min-w-0 flex-wrap items-center justify-center gap-2">{action}</div> : null}
    </div>
  );
};
