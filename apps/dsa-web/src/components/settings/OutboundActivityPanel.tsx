// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useMemo, useState } from 'react';
import type React from 'react';
import { RefreshCw } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { outboundActivityApi } from '../../api/outboundActivity';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import type { LocalOnlyModeStatus, OutboundActivityItem } from '../../types/outboundActivity';
import { getUiLocale } from '../../utils/uiLocale';
import { ApiErrorAlert, Badge, DataTable, type DataTableColumn, EmptyState, IconButton, StatePanel } from '../common';
import { SettingsSectionCard } from './SettingsSectionCard';

type OutboundActivityPanelProps = {
  disabled?: boolean;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  language: UiLanguage;
};

const DEFAULT_LIMIT = 50;

function formatTimestamp(value: string | null | undefined, language: UiLanguage): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(getUiLocale(language), {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false, timeZoneName: 'short',
  }).format(date);
}

const OutboundActivityPanel: React.FC<OutboundActivityPanelProps> = ({ disabled = false, t, language }) => {
  const [status, setStatus] = useState<LocalOnlyModeStatus | null>(null);
  const [items, setItems] = useState<OutboundActivityItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);

  const load = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    setLoadError(null);
    if (mode === 'initial') setIsLoading(true); else setIsRefreshing(true);
    try {
      const [nextStatus, page] = await Promise.all([
        outboundActivityApi.getLocalOnlyStatus(),
        outboundActivityApi.listActivity({ limit: DEFAULT_LIMIT }),
      ]);
      setStatus(nextStatus);
      setItems(page.items);
    } catch (error: unknown) {
      setStatus(null);
      setItems([]);
      setLoadError(getParsedApiError(error));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => { void load('initial'); }, [load]);

  const columns = useMemo<DataTableColumn<OutboundActivityItem>[]>(() => [
    {
      id: 'when',
      header: t('settings.outboundActivityWhen'),
      nowrap: true,
      cell: (item) => formatTimestamp(item.occurredAt, language),
    },
    {
      id: 'decision',
      header: t('settings.outboundActivityDecision'),
      cell: (item) => (
        <Badge variant={item.decision === 'allowed' ? 'success' : 'danger'}>
          {item.decision === 'allowed'
            ? t('settings.outboundActivityAllowed')
            : t('settings.outboundActivityBlocked')}
        </Badge>
      ),
    },
    {
      id: 'class',
      header: t('settings.outboundActivityClass'),
      cell: (item) => (
        <span className="font-mono text-xs">{item.destinationClass}</span>
      ),
    },
    {
      id: 'reason',
      header: t('settings.outboundActivityReason'),
      cell: (item) => (
        <span className="font-mono text-xs">{item.reason}</span>
      ),
    },
    {
      id: 'correlation',
      header: t('settings.outboundActivityCorrelation'),
      cell: (item) => (
        <span className="font-mono text-xs">{item.correlationId}</span>
      ),
    },
  ], [language, t]);

  return (
    <SettingsSectionCard
      title={t('settings.outboundActivityTitle')}
      description={t('settings.outboundActivityDescription')}
      actions={(
        <IconButton
          aria-label={t('settings.outboundActivityRefresh')}
          disabled={disabled || isLoading || isRefreshing}
          onClick={() => { void load('refresh'); }}
        >
          <RefreshCw size={16} className={isRefreshing ? 'animate-spin' : undefined} />
        </IconButton>
      )}
    >
      {status ? (
        <div className="mb-4 flex flex-wrap items-center gap-2" data-testid="settings-local-only-status">
          <Badge variant={status.enabled ? 'warning' : 'default'}>
            {status.enabled ? t('settings.outboundActivityModeOn') : t('settings.outboundActivityModeOff')}
          </Badge>
          <span className="text-sm text-muted-foreground">
            {t('settings.outboundActivityModeHint', { reason: status.blockedErrorReason })}
          </span>
        </div>
      ) : null}
      {loadError ? <ApiErrorAlert error={loadError} className="mb-3" /> : null}
      {isLoading ? (
        <StatePanel state="loading" title={t('common.loading')} />
      ) : items.length === 0 ? (
        <EmptyState title={t('settings.outboundActivityEmptyTitle')} description={t('settings.outboundActivityEmptyDescription')} />
      ) : (
        <div data-testid="settings-outbound-activity-list">
          <DataTable
            caption={t('settings.outboundActivityTitle')}
            frame="embedded"
            density="compact"
            minWidth="content"
            columns={columns}
            rows={items}
            getRowKey={(item) => `${item.correlationId}-${item.occurredAt}`}
            emptyState={{
              title: t('settings.outboundActivityEmptyTitle'),
              description: t('settings.outboundActivityEmptyDescription'),
            }}
          />
          <p className="mt-3 text-xs text-muted-foreground">{t('settings.outboundActivityReadOnlyNote')}</p>
        </div>
      )}
    </SettingsSectionCard>
  );
};

export default OutboundActivityPanel;
