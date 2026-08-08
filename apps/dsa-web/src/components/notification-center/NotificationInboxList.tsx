// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { Activity, Bell, CheckCheck, FlaskConical, TriangleAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { NOTIFICATION_CENTER_TEXT } from '../../locales/notificationCenter';
import type { NotificationInboxItem } from '../../types/notificationInbox';
import { cn } from '../../utils/cn';
import { formatUiDateTime } from '../../utils/uiLocale';
import { Badge, Button, EmptyState } from '../common';

function kindIcon(kind: NotificationInboxItem['kind']) {
  if (kind === 'alert_triggered') return TriangleAlert;
  if (kind === 'decision_signal') return Activity;
  if (kind === 'analysis_complete') return FlaskConical;
  return Bell;
}

export type NotificationInboxListProps = {
  items: readonly NotificationInboxItem[];
  emptyTitle: string;
  emptyDescription: string;
  onMarkRead: (itemId: string) => void;
  markingId?: string | null;
  disabled?: boolean;
};

export function NotificationInboxList({
  items,
  emptyTitle,
  emptyDescription,
  onMarkRead,
  markingId = null,
  disabled = false,
}: NotificationInboxListProps) {
  const { language } = useUiLanguage();
  const text = NOTIFICATION_CENTER_TEXT[language];

  if (items.length === 0) {
    return (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
        icon={<Bell className="size-5" aria-hidden="true" />}
        data-testid="notification-center-empty"
      />
    );
  }

  return (
    <ul className="divide-y divide-border rounded-xl border border-border bg-card" data-testid="notification-center-list">
      {items.map((item) => {
        const Icon = kindIcon(item.kind);
        return (
          <li
            key={item.id}
            className={cn(
              'flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-start sm:justify-between',
              !item.isRead && 'bg-primary/5',
            )}
            data-testid={`notification-center-item-${item.id}`}
          >
            <div className="flex min-w-0 flex-1 items-start gap-3">
              <span
                className={cn(
                  'mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-md',
                  item.severity === 'error' && 'bg-danger/10 text-danger',
                  item.severity === 'warning' && 'bg-warning/10 text-warning',
                  item.severity === 'info' && 'bg-primary/10 text-primary',
                )}
              >
                <Icon className="size-4" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="truncate text-sm font-semibold text-foreground">{item.title}</h3>
                  <Badge variant={item.isRead ? 'history' : 'info'}>
                    {item.isRead ? text.read : text.unread}
                  </Badge>
                </div>
                <p className="mt-1 text-sm text-secondary-text">{item.summary}</p>
                <time className="mt-1 block text-xs text-muted-text" dateTime={item.createdAt}>
                  {formatUiDateTime(item.createdAt, language, {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </time>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2 sm:pt-0.5">
              {!item.isRead ? (
                <Button
                  type="button"
                  variant="outline"
                  size="compact"
                  disabled={disabled || markingId === item.id}
                  onClick={() => onMarkRead(item.id)}
                  aria-label={text.markRead}
                >
                  <CheckCheck className="size-3.5" aria-hidden="true" />
                  {text.markRead}
                </Button>
              ) : null}
              <Link
                to={item.href}
                className="inline-flex h-5 min-w-5 items-center justify-center rounded-md px-2 text-xs font-medium text-primary hover:bg-hover"
              >
                {text.open}
              </Link>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
