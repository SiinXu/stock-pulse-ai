// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Event calendar workspace — independent from alerts (T32) and notifications (T20).

import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarDays } from 'lucide-react';
import { eventCalendarApi } from '../../api/eventCalendar';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import {
  ApiErrorAlert,
  AppPage,
  Badge,
  Button,
  Card,
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
import { EVENT_CALENDAR_TEXT } from '../../locales/eventCalendar';
import type {
  CalendarEventItem,
  EventCalendarResponse,
} from '../../types/eventCalendar';

function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function defaultRange(): { from: string; to: string } {
  const from = new Date();
  const to = new Date();
  to.setDate(to.getDate() + 90);
  return { from: isoDate(from), to: isoDate(to) };
}

function certaintyVariant(certainty: string): 'success' | 'warning' | 'default' {
  if (certainty === 'confirmed') return 'success';
  if (certainty === 'scheduled') return 'warning';
  return 'default';
}

const EventCalendarWorkspace: React.FC = () => {
  const { language } = useUiLanguage();
  const text = EVENT_CALENDAR_TEXT[language];
  const defaults = useMemo(() => defaultRange(), []);
  const [dateFrom, setDateFrom] = useState(defaults.from);
  const [dateTo, setDateTo] = useState(defaults.to);
  const [includeImpact, setIncludeImpact] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [data, setData] = useState<EventCalendarResponse | null>(null);

  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await eventCalendarApi.getCalendar({
        dateFrom,
        dateTo,
        includeImpact,
        reportLanguage: language === 'en' ? 'en' : 'zh',
      });
      setData(response);
    } catch (err) {
      setError(getParsedApiError(err));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, includeImpact, language]);

  useEffect(() => {
    void load();
  }, [load]);

  const certaintyLabel = useCallback(
    (value: string) => {
      if (value === 'confirmed') return text.certaintyConfirmed;
      if (value === 'scheduled') return text.certaintyScheduled;
      if (value === 'estimated') return text.certaintyEstimated;
      return value;
    },
    [text],
  );

  const typeLabel = useCallback(
    (value: string) => {
      switch (value) {
        case 'earnings':
          return text.typeEarnings;
        case 'ex_dividend':
          return text.typeExDividend;
        case 'unlock':
          return text.typeUnlock;
        case 'index_rebalance':
          return text.typeIndexRebalance;
        case 'macro':
          return text.typeMacro;
        default:
          return value;
      }
    },
    [text],
  );

  const columns: DataTableColumn<CalendarEventItem>[] = useMemo(
    () => [
      {
        id: 'date',
        header: text.date,
        cell: (row) => row.eventDate,
      },
      {
        id: 'symbol',
        header: text.symbol,
        cell: (row) => row.symbol,
      },
      {
        id: 'type',
        header: text.eventType,
        cell: (row) => typeLabel(row.eventType),
      },
      {
        id: 'certainty',
        header: text.certainty,
        cell: (row) => (
          <Badge variant={certaintyVariant(row.certainty)}>
            {certaintyLabel(row.certainty)}
          </Badge>
        ),
      },
      {
        id: 'title',
        header: text.titleColumn,
        cell: (row) => row.title,
      },
      {
        id: 'impact',
        header: text.impact,
        cell: (row) => {
          const impact = row.impactPreview;
          if (!impact || !impact.available) {
            return <span className="text-muted-foreground">{text.impactUnavailable}</span>;
          }
          const affected = impact.affected as Record<string, unknown> | null | undefined;
          const bits: string[] = [];
          if (affected?.inWatchlist) bits.push(text.inWatchlist);
          if (affected?.inPortfolio) bits.push(text.inPortfolio);
          return (
            <div className="flex max-w-md flex-col gap-1 text-sm">
              {impact.whyItMatters ? (
                <span>
                  <strong>{text.whyItMatters}:</strong>
                  {' '}
                  {impact.whyItMatters}
                </span>
              ) : null}
              {bits.length > 0 ? <span>{bits.join(' · ')}</span> : null}
            </div>
          );
        },
      },
    ],
    [certaintyLabel, text, typeLabel],
  );

  return (
    <AppPage>
      <PageHeader
        eyebrow={text.eyebrow}
        title={text.title}
        description={text.description}
        actions={(
          <Button type="button" variant="secondary" onClick={() => void load()} disabled={loading}>
            {text.refresh}
          </Button>
        )}
      />

      <Surface className="mb-4 flex flex-wrap items-end gap-4 p-4">
        <DatePicker
          label={text.dateFrom}
          value={dateFrom}
          onChange={setDateFrom}
          ariaLabel={text.dateFrom}
        />
        <DatePicker
          label={text.dateTo}
          value={dateTo}
          onChange={setDateTo}
          ariaLabel={text.dateTo}
        />
        <Checkbox
          label={text.includeImpact}
          checked={includeImpact}
          onChange={(event) => setIncludeImpact(event.currentTarget.checked)}
        />
      </Surface>

      {loading ? <Loading label={text.loading} /> : null}

      {!loading && error ? (
        <ApiErrorAlert
          error={error}
          actionLabel={text.errorRetry}
          onAction={() => {
            void load();
          }}
        />
      ) : null}

      {!loading && !error && data && !data.enabled ? (
        <EmptyState
          icon={<CalendarDays aria-hidden />}
          title={text.disabledTitle}
          description={text.disabledDescription}
        />
      ) : null}

      {!loading && !error && data && data.enabled ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
            <span>{formatUiText(text.symbolCount, { count: data.symbolCount })}</span>
            <span>·</span>
            <span>{formatUiText(text.eventCount, { count: data.eventCount })}</span>
            <span>·</span>
            <span>{data.fetchAttempted ? text.fetchAttempted : text.fetchSkipped}</span>
            {data.fetchedAt ? (
              <>
                <span>·</span>
                <span>
                  {text.fetchedAt}
                  :
                  {' '}
                  {data.fetchedAt}
                </span>
              </>
            ) : null}
          </div>

          {data.coverageNotes.length > 0 ? (
            <InlineAlert
              variant="info"
              title={text.coverageNote}
              message={(
                <ul className="list-disc pl-5">
                  {data.coverageNotes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              )}
            />
          ) : null}

          {data.events.length === 0 ? (
            <EmptyState
              icon={<CalendarDays aria-hidden />}
              title={text.emptyTitle}
              description={text.emptyDescription}
            />
          ) : (
            <DataTable
              caption={text.title}
              captionMode="hidden"
              columns={columns}
              rows={data.events}
              getRowKey={(row) => row.eventId}
              emptyState={{
                title: text.emptyTitle,
                description: text.emptyDescription,
              }}
            />
          )}

          {data.coverage.length > 0 ? (
            <Card className="p-4">
              <h3 className="mb-2 text-base font-semibold">{text.coverageTitle}</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="py-2 pr-3">{text.marketColumn}</th>
                      <th className="py-2 pr-3">{text.typeEarnings}</th>
                      <th className="py-2 pr-3">{text.typeExDividend}</th>
                      <th className="py-2 pr-3">{text.typeUnlock}</th>
                      <th className="py-2 pr-3">{text.typeIndexRebalance}</th>
                      <th className="py-2 pr-3">{text.typeMacro}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.coverage.map((row) => (
                      <tr key={row.market} className="border-b last:border-0">
                        <td className="py-2 pr-3 font-medium">{row.market}</td>
                        <td className="py-2 pr-3">{row.earnings}</td>
                        <td className="py-2 pr-3">{row.exDividend}</td>
                        <td className="py-2 pr-3">{row.unlock}</td>
                        <td className="py-2 pr-3">{row.indexRebalance}</td>
                        <td className="py-2 pr-3">{row.macro}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : null}
        </div>
      ) : null}
    </AppPage>
  );
};

export default EventCalendarWorkspace;
