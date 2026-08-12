// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import type React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { RefreshCw, Settings2 } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import {
  pluginsApi,
  type PluginInfo,
  type PluginLifecycleState,
  type PluginSettingValue,
  type PluginSettingsResponse,
} from '../../api/plugins';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import { SETTINGS_ROUTE_QUERY_KEYS } from '../../routing/routes';
import {
  ApiErrorAlert,
  Badge,
  Button,
  DataTable,
  type DataTableColumn,
  EmptyState,
  IconButton,
  InlineAlert,
  StatePanel,
} from '../common';
import {
  buildNotificationsChannelHref,
  getLinkableNotificationChannelIds,
  pluginClaimsNotificationAdapter,
} from './extensionNotificationLinks';
import { SettingsSwitch } from './SettingsSwitch';
import { SettingsSectionCard } from './SettingsSectionCard';

const PluginSettingsModal = lazy(() => import('./PluginSettingsModal'));

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
  if (plugin.lastErrorCode) {
    return t('settings.loadedExtensionsFailureCode', { code: plugin.lastErrorCode });
  }
  return t('settings.loadedExtensionsFailureReasonUnavailable');
}

function NotificationCapabilityLinks({
  plugin,
  t,
}: {
  plugin: PluginInfo;
  t: LoadedExtensionsPanelProps['t'];
}) {
  if (!pluginClaimsNotificationAdapter(plugin)) return null;
  const channelIds = getLinkableNotificationChannelIds(plugin);
  if (channelIds.length === 0) {
    return (
      <p
        className="text-xs leading-5 text-muted-text"
        data-testid={`loaded-extension-notification-inactive-${plugin.id}`}
      >
        {t('settings.loadedExtensionsNotificationInactive')}
      </p>
    );
  }
  return (
    <div
      className="flex flex-col gap-1"
      data-testid={`loaded-extension-notification-links-${plugin.id}`}
    >
      {channelIds.map((channelId) => (
        <Link
          key={channelId}
          to={buildNotificationsChannelHref(channelId)}
          className="text-xs font-medium text-primary underline-offset-2 hover:underline"
          data-testid={`loaded-extension-notification-link-${plugin.id}-${channelId}`}
        >
          {t('settings.loadedExtensionsOpenNotificationChannel', { channel: channelId })}
        </Link>
      ))}
    </div>
  );
}

const LoadedExtensionsPanel: React.FC<LoadedExtensionsPanelProps> = ({
  disabled = false,
  t,
  language,
}) => {
  const [searchParams] = useSearchParams();
  const focusedPluginId = searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.plugin);
  const [items, setItems] = useState<PluginInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingPluginId, setPendingPluginId] = useState<string | null>(null);
  const [selectedSettings, setSelectedSettings] = useState<PluginSettingsResponse | null>(null);
  const [settingsPluginName, setSettingsPluginName] = useState('');
  const [settingsSaveError, setSettingsSaveError] = useState<string | null>(null);
  const [restartRequired, setRestartRequired] = useState(false);

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

  useEffect(() => {
    if (!focusedPluginId || isLoading) return;
    const row = document.querySelector(
      `[data-testid="loaded-extension-row-${CSS.escape(focusedPluginId)}"]`,
    );
    if (row instanceof HTMLElement) {
      row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [focusedPluginId, isLoading, items]);

  const updateLifecycle = useCallback(async (plugin: PluginInfo, enabled: boolean) => {
    setPendingPluginId(plugin.id);
    setActionError(null);
    try {
      const result = await pluginsApi.updateLifecycle(plugin.id, enabled ? 'enable' : 'disable');
      if (!result.success) {
        setActionError(result.message || result.errorCode || t('common.failure'));
        return;
      }
      setRestartRequired((current) => current || result.restartRequired);
      setItems((current) => current.map((item) => {
        if (item.id !== plugin.id) return item;
        if (result.plugin) return result.plugin;
        return {
          ...item,
          state: result.state,
          desiredEnabled: enabled,
          // Fail closed until the next list refresh confirms active registrations.
          notificationChannels: [],
          extensionPoints: enabled
            ? item.extensionPoints
            : item.extensionPoints.filter((point) => point !== 'notification_channel'),
        };
      }));
    } catch (error: unknown) {
      setActionError(getParsedApiError(error, language).message);
    } finally {
      setPendingPluginId(null);
    }
  }, [language, t]);

  const openSettings = useCallback(async (plugin: PluginInfo) => {
    setPendingPluginId(plugin.id);
    setActionError(null);
    setSettingsSaveError(null);
    try {
      const response = await pluginsApi.getSettings(plugin.id);
      setSettingsPluginName(plugin.name || plugin.id);
      setSelectedSettings(response);
    } catch (error: unknown) {
      setActionError(getParsedApiError(error, language).message);
    } finally {
      setPendingPluginId(null);
    }
  }, [language]);

  const saveSettings = useCallback(async (values: Record<string, PluginSettingValue>) => {
    if (!selectedSettings) return;
    setSettingsSaveError(null);
    try {
      const response = await pluginsApi.updateSettings(
        selectedSettings.pluginId,
        values,
        selectedSettings.maskToken,
      );
      setRestartRequired((current) => current || response.restartRequired);
      setSelectedSettings(null);
    } catch (error: unknown) {
      setSettingsSaveError(getParsedApiError(error, language).message);
      throw error;
    }
  }, [language, selectedSettings]);

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
        <div className="space-y-2">
          {plugin.extensionPoints.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {plugin.extensionPoints.map((point) => (
                <Badge key={point} variant="history" size="sm">
                  {point}
                </Badge>
              ))}
            </div>
          ) : (
            <span className="text-xs text-muted-text">—</span>
          )}
          <NotificationCapabilityLinks plugin={plugin} t={t} />
        </div>
      ),
    },
    {
      id: 'management',
      header: t('settings.loadedExtensionsColNotes'),
      cell: (plugin) => {
        const reason = failureReason(plugin, t);
        return (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <SettingsSwitch
                checked={plugin.desiredEnabled}
                disabled={disabled || pendingPluginId === plugin.id}
                onCheckedChange={(next) => { void updateLifecycle(plugin, next); }}
                aria-label={`${t(plugin.desiredEnabled
                  ? 'settings.loadedExtensionsStateDisabled'
                  : 'settings.loadedExtensionsStateEnabled')}: ${plugin.name || plugin.id}`}
                testId={`plugin-toggle-${plugin.id}`}
              />
              {plugin.settingsCount > 0 ? (
                <Button
                  variant="outline"
                  size="default"
                  disabled={disabled || pendingPluginId === plugin.id}
                  onClick={() => { void openSettings(plugin); }}
                  aria-label={`${t('common.details')}: ${plugin.name || plugin.id}`}
                >
                  <Settings2 aria-hidden="true" className="h-3.5 w-3.5" />
                  {t('common.details')}
                </Button>
              ) : (
                <span aria-hidden="true" className="text-xs text-muted-text">—</span>
              )}
            </div>
            {reason ? (
              <p className="text-xs leading-5 text-warning" data-testid={`loaded-extension-failure-${plugin.id}`}>
                {reason}
              </p>
            ) : null}
          </div>
        );
      },
    },
  ], [disabled, openSettings, pendingPluginId, t, updateLifecycle]);

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

      <p className="text-xs leading-5 text-muted-text" data-testid="settings-loaded-extensions-management-note">
        {t('settings.loadedExtensionsReadOnlyNote')}
      </p>

      {loadError ? <ApiErrorAlert error={loadError} className="mb-3" /> : null}
      {actionError ? (
        <InlineAlert
          className="mb-3"
          variant="danger"
          title={t('common.failure')}
          message={actionError}
        />
      ) : null}
      {restartRequired ? (
        <InlineAlert
          className="mb-3"
          variant="warning"
          title={t('settings.fieldRestartRequired')}
          message={t('settings.loadedExtensionsReadOnlyNote')}
        />
      ) : null}

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
            isRowSelected={(plugin) => focusedPluginId === plugin.id}
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

      {selectedSettings ? (
        <Suspense fallback={null}>
          <PluginSettingsModal
            pluginName={settingsPluginName}
            settings={selectedSettings}
            disabled={disabled}
            saveError={settingsSaveError}
            onClose={() => setSelectedSettings(null)}
            onSave={saveSettings}
            t={t}
          />
        </Suspense>
      ) : null}
    </SettingsSectionCard>
  );
};

export default LoadedExtensionsPanel;
