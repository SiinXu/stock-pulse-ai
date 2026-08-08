// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useMemo, useState } from 'react';
import type React from 'react';
import { RefreshCw } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { pluginsApi, type PluginInfo, type PluginLifecycleState } from '../../api/plugins';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import {
  ApiErrorAlert,
  Badge,
  DataTable,
  type DataTableColumn,
  EmptyState,
  IconButton,
  InlineAlert,
  StatePanel,
} from '../common';
import { SettingsSectionCard } from './SettingsSectionCard';

type LoadedExtensionsPanelProps = {
  disabled?: boolean;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  language: UiLanguage;
};

function stateBadgeVariant(state: PluginLifecycleState): 'success' | 'danger' | 'warning' | 'default' {
  if (state === 'enabled') return 'success';
  if (state === 'failed') return 'danger';
  if (state === 'disabled') return 'warning';
  return 'default';
}

function stateLabel(
  state: PluginLifecycleState,
  t: LoadedExtensionsPanelProps['t'],
): string {
  if (state === 'enabled') return t('settings.loadedExtensionsStateEnabled');
  if (state === 'disabled') return t('settings.loadedExtensionsStateDisabled');
  if (state === 'failed') return t('settings.loadedExtensionsStateFailed');
  return t('settings.loadedExtensionsStateRegistered');
}

function sourceLabel(
  source: PluginInfo['source'],
  t: LoadedExtensionsPanelProps['t'],
): string {
  return source === 'builtin'
    ? t('settings.loadedExtensionsSourceBuiltin')
    : t('settings.loadedExtensionsSourceExternal');
}

function sourcePath(plugin: PluginInfo, t: LoadedExtensionsPanelProps['t']): string {
  if (plugin.packageRoot) return plugin.packageRoot;
  if (plugin.source === 'builtin') return t('settings.loadedExtensionsPathBuiltin');
  return t('settings.loadedExtensionsPathUnknown');
}

function failureReason(plugin: PluginInfo, t: LoadedExtensionsPanelProps['t']): string | null {
  if (plugin.state !== 'failed') return null;
  // GET /api/v1/plugins exposes lifecycle state but not last_error / error_code.
  // Stay honest: surface the failed state and actionable checks without inventing a reason.
  return t('settings.loadedExtensionsFailureReasonUnavailable');
}

const LoadedExtensionsPanel: React.FC<LoadedExtensionsPanelProps> = ({
  disabled = false,
  t,
  language: _language,
}) => {
  void _language;
  const [items, setItems] = useState<PluginInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);

  const load = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    setLoadError(null);
    if (mode === 'initial') setIsLoading(true);
    else setIsRefreshing(true);
    try {
      const response = await pluginsApi.list();
      setItems(response.items);
      setTotal(response.total);
    } catch (error: unknown) {
      setItems([]);
      setTotal(0);
      setLoadError(getParsedApiError(error));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load('initial');
  }, [load]);

  const columns = useMemo<DataTableColumn<PluginInfo>[]>(() => [
    {
      id: 'name',
      header: t('settings.loadedExtensionsColName'),
      rowHeader: true,
      cell: (plugin) => (
        <div className="min-w-0">
          <div className="font-medium text-foreground">{plugin.name || plugin.id}</div>
          <div className="mt-0.5 font-mono text-xs text-muted-text">{plugin.id}</div>
          {plugin.description ? (
            <p className="mt-1 text-xs leading-5 text-secondary-text">{plugin.description}</p>
          ) : null}
        </div>
      ),
    },
    {
      id: 'version',
      header: t('settings.loadedExtensionsColVersion'),
      width: 'compact',
      nowrap: true,
      cell: (plugin) => (
        <span className="font-mono text-xs">{plugin.version || '—'}</span>
      ),
    },
    {
      id: 'source',
      header: t('settings.loadedExtensionsColSource'),
      cell: (plugin) => (
        <div className="min-w-0 space-y-1">
          <Badge variant="default" size="sm">{sourceLabel(plugin.source, t)}</Badge>
          <div className="break-all font-mono text-xs text-muted-text">
            {sourcePath(plugin, t)}
          </div>
        </div>
      ),
    },
    {
      id: 'state',
      header: t('settings.loadedExtensionsColState'),
      width: 'compact',
      cell: (plugin) => (
        <div className="space-y-1">
          <Badge variant={stateBadgeVariant(plugin.state)} size="sm">
            {stateLabel(plugin.state, t)}
          </Badge>
          {!plugin.desiredEnabled ? (
            <div className="text-xs text-muted-text">
              {t('settings.loadedExtensionsDesiredDisabled')}
            </div>
          ) : null}
        </div>
      ),
    },
    {
      id: 'capabilities',
      header: t('settings.loadedExtensionsColCapabilities'),
      cell: (plugin) => (
        plugin.extensionPoints.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {plugin.extensionPoints.map((point) => (
              <Badge key={point} variant="history" size="sm">
                {point}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-xs text-muted-text">—</span>
        )
      ),
    },
    {
      id: 'notes',
      header: t('settings.loadedExtensionsColNotes'),
      cell: (plugin) => {
        const reason = failureReason(plugin, t);
        if (!reason) {
          return <span className="text-xs text-muted-text">—</span>;
        }
        return (
          <p className="text-xs leading-5 text-warning" data-testid={`loaded-extension-failure-${plugin.id}`}>
            {reason}
          </p>
        );
      },
    },
  ], [t]);

  return (
    <SettingsSectionCard
      title={t('settings.loadedExtensionsTitle')}
      description={t('settings.loadedExtensionsDescription')}
      actions={(
        <IconButton
          aria-label={t('settings.loadedExtensionsRefresh')}
          disabled={disabled || isLoading || isRefreshing}
          onClick={() => { void load('refresh'); }}
        >
          <RefreshCw size={16} className={isRefreshing ? 'animate-spin' : undefined} />
        </IconButton>
      )}
    >
      <div data-testid="settings-loaded-extensions-trust">
        <InlineAlert
          variant="warning"
          title={t('settings.loadedExtensionsTrustTitle')}
          message={t('settings.loadedExtensionsTrustBody')}
        />
      </div>

      <p className="text-xs leading-5 text-muted-text" data-testid="settings-loaded-extensions-readonly">
        {t('settings.loadedExtensionsReadOnlyNote')}
      </p>

      {loadError ? <ApiErrorAlert error={loadError} className="mb-3" /> : null}

      {isLoading ? (
        <StatePanel state="loading" title={t('common.loading')} />
      ) : items.length === 0 ? (
        <EmptyState
          title={t('settings.loadedExtensionsEmptyTitle')}
          description={t('settings.loadedExtensionsEmptyDescription')}
        />
      ) : (
        <div data-testid="settings-loaded-extensions-list">
          <p className="mb-2 text-xs text-muted-text">
            {t('settings.loadedExtensionsTotal', { total })}
          </p>
          <DataTable
            caption={t('settings.loadedExtensionsListLabel')}
            columns={columns}
            rows={items}
            getRowKey={(plugin) => plugin.id}
            getRowTestId={(plugin) => `loaded-extension-row-${plugin.id}`}
            emptyState={{
              title: t('settings.loadedExtensionsEmptyTitle'),
              description: t('settings.loadedExtensionsEmptyDescription'),
            }}
            density="compact"
            frame="embedded"
            minWidth="wide"
          />
        </div>
      )}
    </SettingsSectionCard>
  );
};

export default LoadedExtensionsPanel;
