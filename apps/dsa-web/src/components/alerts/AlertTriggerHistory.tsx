import type React from 'react';
import { useEffect, useRef } from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import { Badge, Card, DataTable, type DataTableColumn, IconButton, Pagination } from '../common';
import type { AlertTriggerItem } from '../../types/alerts';
import { getMarketPhaseSummaryLabel } from '../../utils/marketPhase';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { ALERT_HISTORY_CONTROLS_TEXT, ALERT_TRIGGER_TEXT } from '../../locales/alerts';
import { formatUiText } from '../../i18n/uiText';
import { formatUiDateTime, getUiClauseSeparator } from '../../utils/uiLocale';
import type { UiLanguage } from '../../i18n/uiText';
import {
  formatAlertTriggerStatus,
  formatDataQualityLevel,
  formatDataQualityLimitation,
} from '../../utils/dataQualityFormat';

function statusVariant(status: string): 'success' | 'warning' | 'danger' | 'default' {
  if (status === 'triggered') return 'success';
  if (status === 'skipped' || status === 'degraded') return 'warning';
  if (status === 'failed') return 'danger';
  return 'default';
}

function formatNullable(value?: string | number | null): string {
  if (value === null || value === undefined || value === '') return '--';
  return String(value);
}

function renderPhaseQuality(trigger: AlertTriggerItem, language: UiLanguage): React.ReactNode {
  const text = ALERT_TRIGGER_TEXT[language];
  const phase = getMarketPhaseSummaryLabel(trigger.marketPhaseSummary, language);
  const quality = formatDataQualityLevel(
    trigger.analysisContextPackOverview?.dataQuality?.level,
    language,
  );
  const limitations = (trigger.analysisContextPackOverview?.dataQuality?.limitations?.slice(0, 2) ?? [])
    .map((item) => formatDataQualityLimitation(item, language));
  if (!phase && !quality && limitations.length === 0) {
    return <span className="text-xs text-muted-text">--</span>;
  }
  return (
    <div className="space-y-1">
      {phase ? <Badge variant="default">{phase.replace(/^.*?:\s*/, '')}</Badge> : null}
      {quality ? <div className="text-xs text-secondary-text">{formatUiText(text.quality, { quality })}</div> : null}
      {limitations.length ? (
        <div className="max-w-44 text-xs text-muted-text">{limitations.join(getUiClauseSeparator(language))}</div>
      ) : null}
    </div>
  );
}

interface AlertTriggerHistoryProps {
  triggers: AlertTriggerItem[];
  isLoading?: boolean;
  page?: number;
  pageSize?: number;
  total?: number;
  lastUpdated?: string | null;
  onPageChange?: (page: number) => void;
  onRefresh?: () => void;
  selectedTriggerId?: number | null;
}

export const AlertTriggerHistory: React.FC<AlertTriggerHistoryProps> = ({
  triggers,
  isLoading = false,
  page = 1,
  pageSize = 20,
  total = triggers.length,
  lastUpdated = null,
  onPageChange,
  onRefresh,
  selectedTriggerId = null,
}) => {
  const { language } = useUiLanguage();
  const text = ALERT_TRIGGER_TEXT[language];
  const controlsText = ALERT_HISTORY_CONTROLS_TEXT[language];
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const selectedTargetRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (isLoading || selectedTriggerId === null) return;
    const target = selectedTargetRef.current;
    if (!target) return;
    target.focus({ preventScroll: true });
    target.closest('tr')?.scrollIntoView?.({ block: 'center' });
  }, [isLoading, selectedTriggerId, triggers]);
  const triggerColumns: DataTableColumn<AlertTriggerItem>[] = [
    {
      id: 'status',
      header: text.status,
      cell: (trigger) => (
        <Badge variant={statusVariant(trigger.status)}>
          {formatAlertTriggerStatus(trigger.status, language)}
        </Badge>
      ),
    },
    {
      id: 'phaseQuality',
      header: text.phaseQuality,
      cell: (trigger) => renderPhaseQuality(trigger, language),
    },
    {
      id: 'target',
      header: text.target,
      cell: (trigger) => (
        <span
          ref={trigger.id === selectedTriggerId ? selectedTargetRef : undefined}
          tabIndex={trigger.id === selectedTriggerId ? -1 : undefined}
          className="font-mono focus-visible:outline-none"
        >
          {trigger.target}
        </span>
      ),
    },
    {
      id: 'observed',
      header: text.observed,
      cell: (trigger) => formatNullable(trigger.observedValue),
    },
    {
      id: 'threshold',
      header: text.threshold,
      cell: (trigger) => formatNullable(trigger.threshold),
    },
    {
      id: 'dataSource',
      header: text.dataSource,
      cell: (trigger) => formatNullable(trigger.dataSource),
    },
    {
      id: 'dataTime',
      header: text.dataTime,
      cell: (trigger) => (
        <span className="text-xs">
          {formatUiDateTime(trigger.dataTimestamp ?? trigger.triggeredAt, language, { dateStyle: 'medium', timeStyle: 'short' })}
        </span>
      ),
    },
    {
      id: 'reason',
      header: text.reason,
      cell: (trigger) => trigger.reason || trigger.diagnostics || '--',
    },
  ];
  return (
    <Card title={text.title} description={text.subtitle} level="interactive" padding="md">
      <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
        {lastUpdated ? (
          <span className="text-xs text-muted-text">
            {formatUiText(controlsText.lastUpdated, {
              time: formatUiDateTime(lastUpdated, language, { dateStyle: 'medium', timeStyle: 'short' }),
            })}
          </span>
        ) : null}
        {onRefresh ? (
          <IconButton
            type="button"
            size="default"
            variant="ghost"
            aria-label={controlsText.refresh}
            onClick={onRefresh}
            isLoading={isLoading}
          >
            <RefreshCw aria-hidden="true" />
          </IconButton>
        ) : null}
      </div>
      <DataTable<AlertTriggerItem>
        caption={text.title}
        columns={triggerColumns}
        rows={triggers}
        getRowKey={(trigger) => trigger.id}
        isRowSelected={(trigger) => trigger.id === selectedTriggerId}
        getRowTestId={(trigger) => `alert-trigger-row-${trigger.id}`}
        status={isLoading ? { state: 'loading', title: text.loading } : undefined}
        emptyState={{
          icon: <Activity className="h-6 w-6" />,
          title: text.emptyTitle,
          description: text.emptyDescription,
        }}
        density="compact"
        minWidth="wide"
      />
      {onPageChange ? (
        <Pagination
          currentPage={page}
          totalPages={totalPages}
          onPageChange={onPageChange}
          className="mt-4"
        />
      ) : null}
    </Card>
  );
};
