import type React from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import { Badge, Button, Card, DataTable, type DataTableColumn, Pagination } from '../common';
import type { AlertTriggerItem } from '../../types/alerts';
import { getMarketPhaseSummaryLabel } from '../../utils/marketPhase';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { ALERT_HISTORY_CONTROLS_TEXT, ALERT_TRIGGER_TEXT } from '../../locales/alerts';
import { formatUiText } from '../../i18n/uiText';
import { formatUiDateTime, getUiClauseSeparator } from '../../utils/uiLocale';
import type { UiLanguage } from '../../i18n/uiText';

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
  const quality = trigger.analysisContextPackOverview?.dataQuality?.level;
  const limitations = trigger.analysisContextPackOverview?.dataQuality?.limitations?.slice(0, 2) ?? [];
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
}) => {
  const { language } = useUiLanguage();
  const text = ALERT_TRIGGER_TEXT[language];
  const controlsText = ALERT_HISTORY_CONTROLS_TEXT[language];
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const triggerColumns: DataTableColumn<AlertTriggerItem>[] = [
    {
      id: 'status',
      header: text.status,
      cell: (trigger) => (
        <Badge variant={statusVariant(trigger.status)}>
          {text.statuses[trigger.status as keyof typeof text.statuses] ?? trigger.status}
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
      cell: (trigger) => <span className="font-mono">{trigger.target}</span>,
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
    <Card title={text.title} subtitle={text.subtitle} variant="bordered" padding="md">
      <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
        {lastUpdated ? (
          <span className="text-xs text-muted-text">
            {formatUiText(controlsText.lastUpdated, {
              time: formatUiDateTime(lastUpdated, language, { dateStyle: 'medium', timeStyle: 'short' }),
            })}
          </span>
        ) : null}
        {onRefresh ? (
          <Button type="button" size="default" variant="secondary" onClick={onRefresh} isLoading={isLoading} loadingText={text.loading}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            {controlsText.refresh}
          </Button>
        ) : null}
      </div>
      <DataTable<AlertTriggerItem>
        caption={text.title}
        columns={triggerColumns}
        rows={triggers}
        getRowKey={(trigger) => trigger.id}
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
