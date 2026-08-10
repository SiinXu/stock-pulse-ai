// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCheck, RefreshCw } from 'lucide-react';
import { notificationInboxApi } from '../api/notificationInbox';
import { getParsedApiError, type ParsedApiError } from '../api/error';
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
import { formatUiText } from '../i18n/uiText';
import { NOTIFICATION_CENTER_TEXT } from '../locales/notificationCenter';
import type {
  NotificationInboxItem,
  NotificationInboxKind,
  NotificationInboxPage,
} from '../types/notificationInbox';

type ReadFilter = 'all' | 'unread';

const KIND_OPTIONS: Array<{ value: '' | NotificationInboxKind; labelKey: keyof typeof NOTIFICATION_CENTER_TEXT['en'] }> = [
  { value: '', labelKey: 'kindAll' },
  { value: 'analysis_complete', labelKey: 'kindAnalysis' },
  { value: 'alert_triggered', labelKey: 'kindAlert' },
  { value: 'scheduled_task_result', labelKey: 'kindScheduled' },
  { value: 'decision_signal', labelKey: 'kindSignal' },
];

const NotificationCenterPage: React.FC = () => {
  const { language, t } = useUiLanguage();
  const text = NOTIFICATION_CENTER_TEXT[language];
  const [pageData, setPageData] = useState<NotificationInboxPage | null>(null);
  const [items, setItems] = useState<NotificationInboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [readFilter, setReadFilter] = useState<ReadFilter>('all');
  const [kind, setKind] = useState<'' | NotificationInboxKind>('');
  const [markingId, setMarkingId] = useState<string | null>(null);
  const [markingAll, setMarkingAll] = useState(false);

  const load = useCallback(async (
    mode: 'initial' | 'refresh' | 'more' = 'initial',
    cursor?: string,
  ) => {
    if (mode === 'initial') setLoading(true);
    if (mode === 'refresh') setRefreshing(true);
    if (mode === 'more') setLoadingMore(true);
    setError(null);
    try {
      const response = await notificationInboxApi.list({
        page: 1,
        pageSize: 50,
        cursor,
        kind: kind || undefined,
        unreadOnly: readFilter === 'unread',
      });
      setPageData(response);
      setItems((current) => {
        if (mode !== 'more') return response.items;
        const existingIds = new Set(current.map((item) => item.id));
        return [...current, ...response.items.filter((item) => !existingIds.has(item.id))];
      });
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
    }
  }, [kind, readFilter]);

  useEffect(() => {
    void load('initial');
  }, [load]);

  const handleMarkRead = async (itemId: string) => {
    setMarkingId(itemId);
    setError(null);
    try {
      await notificationInboxApi.markRead([itemId]);
      await load('refresh');
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setMarkingId(null);
    }
  };

  const handleMarkAllRead = async () => {
    setMarkingAll(true);
    setError(null);
    try {
      await notificationInboxApi.markAllRead(kind || undefined);
      await load('refresh');
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setMarkingAll(false);
    }
  };

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
          <ApiErrorAlert error={error} />
        </div>
      ) : null}

      {hasPartialSource ? (
        <div
          className="mb-4 rounded-md border border-warning/35 bg-warning/10 px-4 py-3 text-sm text-secondary-text"
          role="status"
          data-testid="notification-center-partial-source"
        >
          {text.partialSourceWarning}
        </div>
      ) : null}

      {loading ? (
        <p className="py-12 text-center text-sm text-secondary-text" role="status">
          {t('common.loading')}
        </p>
      ) : (
        <>
          <NotificationInboxList
            items={items}
            emptyTitle={emptyTitle}
            emptyDescription={emptyDescription}
            onMarkRead={(itemId) => void handleMarkRead(itemId)}
            markingId={markingId}
            disabled={markingAll || loadingMore}
          />
          {pageData?.hasMore && pageData.nextCursor ? (
            <div className="mt-4 flex justify-center">
              <Button
                type="button"
                variant="outline"
                onClick={() => void load('more', pageData.nextCursor ?? undefined)}
                disabled={loadingMore}
              >
                <RefreshCw className={loadingMore ? 'size-4 animate-spin' : 'size-4'} aria-hidden="true" />
                {loadingMore ? text.loadingMore : text.loadMore}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </WorkspacePage>
  );
};

export default NotificationCenterPage;
