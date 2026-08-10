// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { Activity, Bell, BellRing, FlaskConical, TriangleAlert } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { useUnreadNotifications } from '../../hooks/useUnreadNotifications';
import { formatUiText } from '../../i18n/uiText';
import { NOTIFICATION_CENTER_TEXT } from '../../locales/notificationCenter';
import { NOTIFICATIONS_TEXT } from '../../locales/notifications';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import type { NotificationInboxItem } from '../../types/notificationInbox';
import { cn } from '../../utils/cn';
import { formatUiDateTime } from '../../utils/uiLocale';
import { IconButton } from '../common/IconButton';
import { Popover } from '../common/Popover';

const MAX_VISIBLE_ITEMS = 10;

function NotificationTimestamp({ value }: { value: string }) {
  const { language } = useUiLanguage();
  return (
    <time className="shrink-0 text-xs text-muted-text" dateTime={value}>
      {formatUiDateTime(value, language, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })}
    </time>
  );
}

function NotificationKindIcon({ kind }: { kind: NotificationInboxItem['kind'] }) {
  const props = { className: 'size-3.5', 'aria-hidden': true } as const;
  if (kind === 'alert_triggered') return <TriangleAlert {...props} />;
  if (kind === 'decision_signal') return <Activity {...props} />;
  if (kind === 'analysis_complete') return <FlaskConical {...props} />;
  return <Bell {...props} />;
}

function NotificationRow({ item, close }: { item: NotificationInboxItem; close: () => void }) {
  const { language } = useUiLanguage();
  const text = NOTIFICATION_CENTER_TEXT[language];
  const title = formatUiText(text[item.titleKey], item.titleParams);
  return (
    <Link
      to={item.href}
      onClick={close}
      className={cn(
        'flex min-h-14 items-start gap-3 px-4 py-2.5 transition-colors hover:bg-hover focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25',
        !item.isRead && 'bg-primary/5',
      )}
    >
      <span
        className={cn(
          'mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md',
          item.severity === 'error' && 'bg-danger/10 text-danger',
          item.severity === 'warning' && 'bg-warning/10 text-warning',
          item.severity === 'info' && 'bg-primary/10 text-primary',
        )}
      >
        <NotificationKindIcon kind={item.kind} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex min-w-0 items-baseline justify-between gap-2">
          <span className="truncate text-sm font-medium text-foreground">{title}</span>
          <NotificationTimestamp value={item.createdAt} />
        </span>
        <span className="mt-0.5 block truncate text-xs text-secondary-text">{item.summary}</span>
      </span>
    </Link>
  );
}

export type NotificationBellProps = {
  className?: string;
  placement?: 'auto' | 'top' | 'bottom' | 'right';
};

export function NotificationBell({
  className,
  placement = 'bottom',
}: NotificationBellProps) {
  const { language, t } = useUiLanguage();
  const text = NOTIFICATIONS_TEXT[language];
  const [open, setOpen] = useState(false);
  const markedForCurrentOpenRef = useRef(false);
  const notifications = useUnreadNotifications();
  const { isLoading, markAllSeen } = notifications;
  const hasItems = notifications.items.length > 0;
  const triggerLabel = notifications.unreadCount > 0
    ? formatUiText(text.bellLabelWithUnread, { count: notifications.unreadCount })
    : text.bellLabel;

  useEffect(() => {
    if (!open) {
      markedForCurrentOpenRef.current = false;
      return;
    }
    if (!isLoading && !markedForCurrentOpenRef.current) {
      markedForCurrentOpenRef.current = true;
      void markAllSeen().catch(() => undefined);
    }
  }, [isLoading, markAllSeen, open]);

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      placement={placement}
      align="end"
      contentRole="dialog"
      ariaLabel={text.bellLabel}
      rootClassName={className}
      contentClassName="w-[min(22rem,calc(100vw-1.5rem))]"
      trigger={({ toggle }) => (
        <IconButton
          variant="outline"
          size="navigation"
          onClick={toggle}
          aria-label={triggerLabel}
          aria-expanded={open}
          tooltip={triggerLabel}
          className="bg-card shadow-soft-card"
        >
          {notifications.unreadCount > 0 ? <BellRing aria-hidden="true" /> : <Bell aria-hidden="true" />}
          {notifications.unreadCount > 0 ? (
            <span
              data-testid="notification-unread-badge"
              className="absolute -right-1 -top-1 flex min-h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-xs font-semibold leading-none text-white"
              aria-hidden="true"
            >
              {notifications.unreadCount > 99 ? '99+' : notifications.unreadCount}
            </span>
          ) : null}
        </IconButton>
      )}
    >
      {({ close }) => (
        <div className="flex max-h-[min(34rem,calc(100dvh-5rem))] flex-col">
          <header className="flex h-12 shrink-0 items-center border-b border-border px-4">
            <h2 className="text-sm font-semibold text-foreground">{text.bellLabel}</h2>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto">
            {notifications.hasPartialError ? (
              <div
                className="flex items-center justify-between gap-3 border-b border-warning/35 bg-warning/10 px-4 py-2"
                role="status"
              >
                <p className="text-xs text-secondary-text">{text.partialUnavailable}</p>
                <button
                  type="button"
                  onClick={notifications.refresh}
                  className="shrink-0 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-hover"
                >
                  {t('common.retry')}
                </button>
              </div>
            ) : null}
            {notifications.isLoading && !hasItems ? (
              <div className="px-4 py-8 text-center text-sm text-secondary-text" role="status">
                {t('common.loading')}
              </div>
            ) : notifications.hasError ? (
              <div className="flex flex-col items-center gap-3 px-4 py-8 text-center" role="alert">
                <p className="text-sm text-secondary-text">{text.unavailable}</p>
                <button
                  type="button"
                  onClick={notifications.refresh}
                  className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-hover"
                >
                  {t('common.retry')}
                </button>
              </div>
            ) : !hasItems ? (
              <p className="px-4 py-8 text-center text-sm text-secondary-text">{t('common.noData')}</p>
            ) : (
              <div className="divide-y divide-border">
                {notifications.items.slice(0, MAX_VISIBLE_ITEMS).map((item) => (
                  <NotificationRow key={item.id} item={item} close={close} />
                ))}
              </div>
            )}
          </div>

          <Link
            to={APP_ROUTE_PATHS.notifications}
            onClick={close}
            className="flex min-h-11 shrink-0 items-center justify-center border-t border-border px-4 text-sm font-medium text-primary hover:bg-hover focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25"
          >
            {text.viewAll}
          </Link>
        </div>
      )}
    </Popover>
  );
}
