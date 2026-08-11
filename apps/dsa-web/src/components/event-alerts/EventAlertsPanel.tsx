// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { alertsApi } from '../../api/alerts';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import type { AlertTriggerItem } from '../../types/alerts';
import type { EventAlertDisplayItem, EventAlertImpactGrade } from '../../types/eventAlerts';
import { projectCorporateEventAlerts } from '../../utils/eventAlertContext';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { EVENT_ALERT_PAGE_TEXT } from '../../locales/eventAlerts';
import { formatUiText } from '../../i18n/uiText';
import { ApiErrorAlert, AppPage, Button, PageHeader, Select, Toolbar } from '../common';
import { EventAlertDetail } from './EventAlertDetail';
import { EventAlertList } from './EventAlertList';

export type EventAlertsPanelProps = {
  items?: EventAlertDisplayItem[];
  isLoading?: boolean;
  error?: ParsedApiError | null;
  embedded?: boolean;
  onRefresh?: () => void;
};

export const EventAlertsPanel: React.FC<EventAlertsPanelProps> = ({
  items: controlledItems, isLoading: controlledLoading, error: controlledError = null, embedded = false, onRefresh,
}) => {
  const { language } = useUiLanguage();
  const text = EVENT_ALERT_PAGE_TEXT[language];
  const isControlled = controlledItems !== undefined;
  const [remoteTriggers, setRemoteTriggers] = useState<AlertTriggerItem[]>([]);
  const [remoteLoading, setRemoteLoading] = useState(!isControlled);
  const [remoteError, setRemoteError] = useState<ParsedApiError | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [gradeFilter, setGradeFilter] = useState<'all' | EventAlertImpactGrade>('all');

  const loadRemote = async () => {
    if (isControlled) return;
    setRemoteLoading(true);
    setRemoteError(null);
    try {
      const response = await alertsApi.listTriggers({ page: 1, pageSize: 50, status: 'triggered' });
      setRemoteTriggers(response.items ?? []);
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
  useEffect(() => {
    if (items.length === 0) { setSelectedId(null); return; }
    if (selectedId != null && items.some((item) => item.id === selectedId)) return;
    setSelectedId(items[0]?.id ?? null);
  }, [items, selectedId]);

  const selected = items.find((item) => item.id === selectedId) ?? null;
  const isLoading = isControlled ? Boolean(controlledLoading) : remoteLoading;
  const error = isControlled ? controlledError : remoteError;
  const Root: React.ElementType = embedded ? 'div' : AppPage;

  return (
    <Root className="max-w-none space-y-5" data-testid="event-alerts-panel">
      {!embedded ? (
        <PageHeader title={text.title} description={text.description} actions={(
          <Button type="button" variant="secondary" size="default" onClick={() => { if (onRefresh) onRefresh(); else void loadRemote(); }} isLoading={isLoading} loadingText={text.loading}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />{text.refresh}
          </Button>
        )} />
      ) : null}
      <Toolbar aria-label={text.title} left={(
        <Select label={text.status} value={gradeFilter} onChange={(value) => setGradeFilter(value as 'all' | EventAlertImpactGrade)} options={[
          { value: 'all', label: text.filterAll }, { value: 'major', label: text.filterMajor }, { value: 'routine', label: text.filterRoutine },
        ]} />
      )} right={<span className="text-xs text-muted-text">{formatUiText(text.subtitle, { count: String(items.length) })}</span>} />
      {error ? <ApiErrorAlert error={error} onDismiss={() => { if (!isControlled) setRemoteError(null); }} /> : null}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <EventAlertList items={items} isLoading={isLoading} selectedId={selectedId} gradeFilter={gradeFilter} onSelect={(item) => setSelectedId(item.id)} />
        <EventAlertDetail item={selected} />
      </div>
    </Root>
  );
};
