// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo, useRef } from 'react';
import { useRouteFocusTarget } from '../components/routing';
import { APP_ROUTE_PATHS } from '../routing/routes';
import { CheckCheck, RefreshCw } from 'lucide-react';
import {
  ApiErrorAlert,
  Badge,
  Button,
  PageHeader,
  SegmentedControl,
  Select,
  WorkspacePage,
} from '../components/common';
import { NotificationInboxList } from '../components/notification-center';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { useNotificationCenterInbox } from '../hooks/useNotificationCenterInbox';
import { formatUiText } from '../i18n/uiText';
import { NOTIFICATION_CENTER_TEXT } from '../locales/notificationCenter';
import { NOTIFICATIONS_TEXT } from '../locales/notifications';
import type { NotificationInboxKind } from '../types/notificationInbox';

const KIND_OPTIONS: Array<{ value: '' | NotificationInboxKind; labelKey: keyof typeof NOTIFICATION_CENTER_TEXT['en'] }> = [
  { value: '', labelKey: 'kindAll' },
  { value: 'analysis_complete', labelKey: 'kindAnalysis' },
  { value: 'alert_triggered', labelKey: 'kindAlert' },
  { value: 'scheduled_task_result', labelKey: 'kindScheduled' },
  { value: 'decision_signal', labelKey: 'kindSignal' },
  { value: 'daily_brief', labelKey: 'kindDailyBrief' },
  { value: 'high_disagreement', labelKey: 'kindHighDisagreement' },
  { value: 'portfolio_health', labelKey: 'kindPortfolioHealth' },
];

const NotificationCenterPage: React.FC = () => {
  const { language, t } = useUiLanguage();
  const pageHeadingRef = useRef<HTMLHeadingElement>(null);
  useRouteFocusTarget({
    routeId: APP_ROUTE_PATHS.notifications,
    headingRef: pageHeadingRef,
    ready: true,
  });
  const text = NOTIFICATION_CENTER_TEXT[language];
  const notificationText = NOTIFICATIONS_TEXT[language];
  const {
    items,
    pageData,
    loading,
    refreshing,
    loadingMore,
    error,
    readFilter,
    setReadFilter,
    kind,
    setKind,
    markingId,
    markingAll,
    load,
    handleMarkRead,
    handleMarkAllRead,
  } = useNotificationCenterInbox();

  const kindSelectOptions = useMemo(
    () => KIND_OPTIONS.map((option) => ({
      value: option.value,
      label: text[option.labelKey],
    })),
    [text],
  );

  const emptyTitle = readFilter === 'unread' || kind
    ? text.emptyFilteredTitle
    : text.emptyTitle;
  const emptyDescription = readFilter === 'unread' || kind
    ? text.emptyFilteredDescription
    : text.emptyDescription;
  const hasPartialSource = pageData?.sourceStatuses?.some((status) => !status.available) ?? false;

  return (
    <WorkspacePage data-testid="notification-center-page">
      <PageHeader
        ref={pageHeadingRef}
        title={text.title}
        description={text.description}
        actions={(
          <div className="flex flex-wrap items-center gap-2">
            {pageData ? (
              <Badge variant="info" data-testid="notification-center-unread-badge">
                {formatUiText(text.unreadBadge, { count: pageData.unreadTotal })}
              </Badge>
            ) : null}
            <Button
              type="button"
              variant="outline"
              size="compact"
              onClick={() => void load('refresh')}
              disabled={loading || refreshing}
            >
              <RefreshCw className={refreshing ? 'size-3.5 animate-spin' : 'size-3.5'} aria-hidden="true" />
              {text.refresh}
            </Button>
            <Button
              type="button"
              variant="primary"
              size="compact"
              onClick={() => void handleMarkAllRead()}
              disabled={loading || markingAll || (pageData?.unreadTotal ?? 0) === 0}
            >
              <CheckCheck className="size-3.5" aria-hidden="true" />
              {text.markAllRead}
            </Button>
          </div>
        )}
      />

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SegmentedControl
          ariaLabel={text.filterAll}
          value={readFilter}
          onChange={(value) => setReadFilter(value)}
          options={[
            { value: 'all', label: text.filterAll },
            { value: 'unread', label: text.filterUnread },
          ]}
        />
        <div className="w-full sm:w-56">
          <Select
            ariaLabel={text.kindAll}
            value={kind}
            onChange={(value) => setKind(value as '' | NotificationInboxKind)}
            options={kindSelectOptions}
          />
        </div>
      </div>

      {pageData ? (
        <p className="mb-3 text-xs text-muted-text">
          {formatUiText(text.retentionHint, {
            days: pageData.retentionDays,
            max: pageData.maxItems,
          })}
        </p>
      ) : null}

      {error ? (
        <div className="mb-4" role="alert" aria-label={text.loadError}>
          <ApiErrorAlert
            error={error}
            actionLabel={t('common.retry')}
            onAction={() => void load('initial')}
          />
        </div>
      ) : null}

      {hasPartialSource ? (
        <div
          className="mb-4 rounded-md border border-warning/35 bg-warning/10 px-4 py-3 text-sm text-secondary-text"
          role="status"
          data-testid="notification-center-partial-source"
        >
          {notificationText.partialUnavailable}
        </div>
      ) : null}

      {loading ? (
        <p className="py-12 text-center text-sm text-secondary-text" role="status">
          {t('common.loading')}
        </p>
      ) : !error || items.length > 0 ? (
        <>
          <NotificationInboxList
            items={items}
            emptyTitle={emptyTitle}
            emptyDescription={emptyDescription}
            onMarkRead={(itemId) => void handleMarkRead(itemId)}
            markingId={markingId}
            disabled={markingAll || loadingMore}
          />
          {!error && pageData?.hasMore && pageData.nextCursor ? (
            <div className="mt-4 flex justify-center">
              <Button
                type="button"
                variant="outline"
                onClick={() => void load('more', pageData.nextCursor ?? undefined)}
                disabled={loadingMore}
              >
                <RefreshCw className={loadingMore ? 'size-4 animate-spin' : 'size-4'} aria-hidden="true" />
                {loadingMore ? t('common.loading') : text.loadMore}
              </Button>
            </div>
          ) : null}
        </>
      ) : null}
    </WorkspacePage>
  );
};

export default NotificationCenterPage;
