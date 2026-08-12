// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CalendarDays, RefreshCw } from 'lucide-react';
import { alertsApi } from '../../api/alerts';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import type { AlertTriggerItem } from '../../types/alerts';
import type { EventAlertDisplayItem, EventAlertImpactGrade } from '../../types/eventAlerts';
import { projectCorporateEventAlerts } from '../../utils/eventAlertContext';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { EVENT_ALERT_PAGE_TEXT } from '../../locales/eventAlerts';
import { EVENT_CALENDAR_TEXT } from '../../locales/eventCalendar';
import { formatUiText } from '../../i18n/uiText';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import { ApiErrorAlert, AppPage, Button, PageHeader, Select, Toolbar } from '../common';
import EventAlertDetail from './EventAlertDetail';
import EventAlertList from './EventAlertList';

export type EventAlertsPanelProps = {
  items?: EventAlertDisplayItem[];
  isLoading?: boolean;
  error?: ParsedApiError | null;
  embedded?: boolean;
  onRefresh?: () => void;
};

const EventAlertsPanel: React.FC<EventAlertsPanelProps> = ({
  items: controlledItems, isLoading: controlledLoading, error: controlledError = null, embedded = false, onRefresh,
}) => {
  const navigate = useNavigate();
  const { language } = useUiLanguage();
  const text = EVENT_ALERT_PAGE_TEXT[language];
  const calendarText = EVENT_CALENDAR_TEXT[language];
  const isControlled = controlledItems !== undefined;
  const [remoteTriggers, setRemoteTriggers] = useState<AlertTriggerItem[]>([]);
  const [remoteTotal, setRemoteTotal] = useState(0);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [remoteLoading, setRemoteLoading] = useState(!isControlled);
  const [remoteError, setRemoteError] = useState<ParsedApiError | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [gradeFilter, setGradeFilter] = useState<'all' | EventAlertImpactGrade>('all');

  const loadRemote = async ({ append = false }: { append?: boolean } = {}) => {
    if (isControlled) return;
    setRemoteLoading(true);
    setRemoteError(null);
    try {
      const response = await alertsApi.listTriggers({
        alertType: 'corporate_event',
        ...(append && nextCursor ? { cursor: nextCursor } : {}),
        page: 1,
        pageSize: 20,
        status: 'triggered',
      });
      setRemoteTriggers((current) => (append ? [...current, ...(response.items ?? [])] : (response.items ?? [])));
      setRemoteTotal(response.total);
      setNextCursor(response.nextCursor ?? null);
    } catch (error) {
      setRemoteError(getParsedApiError(error));
    } finally {
      setRemoteLoading(false);
    }
  };

  useEffect(() => { if (!embedded) document.title = text.documentTitle; }, [embedded, text.documentTitle]);
  useEffect(() => {
    if (isControlled) return undefined;
    void loadRemote();
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isControlled]);

  const items = useMemo(() => (isControlled ? (controlledItems ?? []) : projectCorporateEventAlerts(remoteTriggers)), [controlledItems, isControlled, remoteTriggers]);
  const visibleItems = useMemo(
    () => (gradeFilter === 'all' ? items : items.filter((item) => item.impactGrade === gradeFilter)),
    [gradeFilter, items],
  );
  useEffect(() => {
    if (visibleItems.length === 0) { setSelectedId(null); return; }
    if (selectedId != null && visibleItems.some((item) => item.id === selectedId)) return;
    setSelectedId(visibleItems[0]?.id ?? null);
  }, [selectedId, visibleItems]);

  const selected = visibleItems.find((item) => item.id === selectedId) ?? null;
  const isLoading = isControlled ? Boolean(controlledLoading) : remoteLoading;
  const error = isControlled ? controlledError : remoteError;
  const Root: React.ElementType = embedded ? 'div' : AppPage;

  return (
    <Root className="max-w-none space-y-5" data-testid="event-alerts-panel">
      {!embedded ? (
        <PageHeader title={text.title} description={text.description} actions={(
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="secondary"
              size="default"
              data-testid="event-alerts-open-calendar"
              onClick={() => navigate(APP_ROUTE_PATHS.eventCalendar)}
            >
              <CalendarDays className="h-4 w-4" aria-hidden="true" />
              {calendarText.title}
            </Button>
            <Button type="button" variant="secondary" size="default" onClick={() => { if (onRefresh) onRefresh(); else void loadRemote({ append: false }); }} isLoading={isLoading} loadingText={text.loading}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />{text.refresh}
            </Button>
          </div>
        )} />
      ) : null}
      <Toolbar aria-label={text.title} left={(
        <Select label={text.status} value={gradeFilter} onChange={(value) => setGradeFilter(value as 'all' | EventAlertImpactGrade)} options={[
          { value: 'all', label: text.filterAll }, { value: 'major', label: text.filterMajor }, { value: 'routine', label: text.filterRoutine }, { value: 'unclassified', label: text.filterUnclassified },
        ]} />
      )} right={<span className="text-xs text-muted-text">{formatUiText(text.subtitle, { count: String(isControlled ? items.length : remoteTotal) })}</span>} />
      {error ? <ApiErrorAlert error={error} onDismiss={() => { if (!isControlled) setRemoteError(null); }} /> : null}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          <EventAlertList items={visibleItems} isLoading={isLoading} selectedId={selectedId} onSelect={(item) => setSelectedId(item.id)} />
          {!isControlled && nextCursor ? (
            <Button type="button" variant="secondary" onClick={() => void loadRemote({ append: true })} isLoading={isLoading} loadingText={text.loadingMore}>
              {text.loadMore}
            </Button>
          ) : null}
        </div>
        <EventAlertDetail item={selected} />
      </div>
    </Root>
  );
};

export default EventAlertsPanel;
