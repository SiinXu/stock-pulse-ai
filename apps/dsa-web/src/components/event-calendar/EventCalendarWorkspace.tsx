// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { BellRing, CalendarDays } from 'lucide-react';
import { eventCalendarApi } from '../../api/eventCalendar';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import {
  ApiErrorAlert,
  AppPage,
  Badge,
  Button,
  Checkbox,
  DataTable,
  type DataTableColumn,
  DatePicker,
  EmptyState,
  InlineAlert,
  Loading,
  PageHeader,
  Surface,
} from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { EVENT_ALERT_PAGE_TEXT } from '../../locales/eventAlerts';
import { EVENT_CALENDAR_TEXT } from '../../locales/eventCalendar';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import type { CalendarEventItem, CorporateEventCategory, EventCalendarResponse } from '../../types/eventCalendar';

function isoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function defaultRange(): { from: string; to: string } {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - 30);
  return { from: isoDate(from), to: isoDate(to) };
}

function statusVariant(status: string, degraded: boolean): 'success' | 'warning' | 'danger' | 'default' {
  if (degraded) return 'warning';
  if (status === 'triggered') return 'success';
  if (status === 'failed') return 'danger';
  return 'default';
}

function isCancelled(error: unknown): boolean {
  return Boolean(error && typeof error === 'object' && 'code' in error
    && (error as { code?: unknown }).code === 'ERR_CANCELED');
}

const EventCalendarWorkspace: React.FC = () => {
  const { language } = useUiLanguage();
  const text = EVENT_CALENDAR_TEXT[language];
  const alertsText = EVENT_ALERT_PAGE_TEXT[language];
  const defaults = useMemo(() => defaultRange(), []);
  const [dateFrom, setDateFrom] = useState(defaults.from);
  const [dateTo, setDateTo] = useState(defaults.to);
  const [includeImpact, setIncludeImpact] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [data, setData] = useState<EventCalendarResponse | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const generationRef = useRef(0);

  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  const load = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setLoading(true);
    setError(null);
    try {
      const response = await eventCalendarApi.getCalendar(
        { dateFrom, dateTo },
        { signal: controller.signal },
      );
      if (generation === generationRef.current) setData(response);
    } catch (caught) {
      if (!controller.signal.aborted && !isCancelled(caught) && generation === generationRef.current) {
        setError(getParsedApiError(caught));
        setData(null);
      }
    } finally {
      if (generation === generationRef.current) setLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => {
    void load();
    return () => requestRef.current?.abort();
  }, [load]);

  const categoryLabel = useCallback((category?: CorporateEventCategory | null) => {
    if (!category) return text.categoryUnknown;
    return text.categories[category];
  }, [text]);

  const statusLabel = useCallback((status: string, degraded: boolean) => {
    if (degraded) return text.statusDegraded;
    if (status === 'triggered') return text.statusTriggered;
    if (status === 'failed') return text.statusFailed;
    if (status === 'skipped') return text.statusSkipped;
    return status;
  }, [text]);

  const columns: DataTableColumn<CalendarEventItem>[] = useMemo(() => {
    const base: DataTableColumn<CalendarEventItem>[] = [
      { id: 'date', header: text.date, cell: (row) => row.eventDate, nowrap: true },
      { id: 'symbol', header: text.symbol, cell: (row) => row.symbol, nowrap: true },
      { id: 'category', header: text.eventType, cell: (row) => categoryLabel(row.eventCategory) },
      {
        id: 'status',
        header: text.status,
        cell: (row) => (
          <Badge variant={statusVariant(row.status, row.degraded)}>
            {statusLabel(row.status, row.degraded)}
          </Badge>
        ),
      },
      { id: 'event', header: text.titleColumn, cell: (row) => row.whatHappened || text.eventUnavailable },
    ];
    if (includeImpact) {
      base.push({
        id: 'impact',
        header: text.impact,
        cell: (row) => (
          <div className="flex max-w-md flex-col gap-1 text-sm">
            <span>{row.whyItMatters || text.impactUnavailable}</span>
            {row.inWatchlist || row.inPortfolio ? (
              <span className="text-muted-foreground">
                {[row.inWatchlist ? text.inWatchlist : '', row.inPortfolio ? text.inPortfolio : '']
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            ) : null}
          </div>
        ),
      });
    }
    base.push({ id: 'source', header: text.source, cell: (row) => row.source || text.sourceUnavailable });
    return base;
  }, [categoryLabel, includeImpact, statusLabel, text]);

  const hasPartialFailure = Boolean(data?.partialErrors.length);

  return (
    <AppPage>
      <PageHeader
        eyebrow={text.eyebrow}
        title={text.title}
        description={text.description}
        actions={(
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={APP_ROUTE_PATHS.eventAlerts}
              data-testid="event-calendar-open-event-alerts"
              data-control="navigation-link"
              className="control-hit-target inline-flex min-h-7 items-center gap-2 rounded-md border border-border bg-hover px-2.5 text-sm font-medium text-foreground shadow-soft-card hover:bg-subtle-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25 dark:bg-border dark:hover:bg-subtle-active"
            >
              <BellRing className="h-4 w-4" aria-hidden="true" />
              <span data-testid="event-calendar-open-alerts">{alertsText.title}</span>
            </Link>
            <Button type="button" variant="secondary" onClick={() => void load()}>
              {text.refresh}
            </Button>
          </div>
        )}
      />

      <Surface className="mb-4 flex flex-wrap items-end gap-4 p-4">
        <DatePicker label={text.dateFrom} value={dateFrom} onChange={setDateFrom} ariaLabel={text.dateFrom} />
        <DatePicker label={text.dateTo} value={dateTo} onChange={setDateTo} ariaLabel={text.dateTo} />
        <Checkbox
          label={text.includeImpact}
          checked={includeImpact}
          onChange={(event) => setIncludeImpact(event.currentTarget.checked)}
        />
      </Surface>

      {loading ? <Loading label={text.loading} /> : null}
      {!loading && error ? (
        <ApiErrorAlert error={error} actionLabel={text.errorRetry} onAction={() => void load()} />
      ) : null}

      {!loading && !error && data ? (
        <div className="flex flex-col gap-4">
          <div className="text-sm text-muted-foreground">
            {formatUiText(text.resultSummary, { count: data.events.length, loaded: data.loadedCount, total: data.total })}
          </div>
          {hasPartialFailure ? (
            <InlineAlert
              variant="warning"
              title={text.partialTitle}
              message={data.partialErrors.includes('event_calendar_result_limit_reached')
                ? text.resultLimitReached
                : text.partialDescription}
            />
          ) : null}
          {data.events.length === 0 ? (
            <EmptyState
              icon={<CalendarDays aria-hidden />}
              title={hasPartialFailure ? text.incompleteTitle : text.emptyTitle}
              description={hasPartialFailure ? text.incompleteDescription : text.emptyDescription}
            />
          ) : (
            <DataTable
              caption={text.title}
              captionMode="hidden"
              columns={columns}
              rows={data.events}
              getRowKey={(row) => row.eventId}
              emptyState={{ title: text.emptyTitle, description: text.emptyDescription }}
              minWidth="wide"
            />
          )}
        </div>
      ) : null}
    </AppPage>
  );
};

export default EventCalendarWorkspace;
