// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useState } from 'react';
import type React from 'react';
import { RefreshCw, RotateCcw } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../../api/error';
import {
  pluginsApi,
  type PluginInfo,
  type PluginLifecycleResponse,
  type PluginLifecycleState,
} from '../../../api/plugins';
import type { UiLanguage, UiTextKey } from '../../../i18n/uiText';
import {
  ApiErrorAlert,
  Badge,
  Button,
  EmptyState,
  IconButton,
  StatePanel,
} from '../../common';
import { SettingsSwitch } from '../SettingsSwitch';
import { SettingsSectionCard } from '../SettingsSectionCard';

type PluginsPanelProps = {
  disabled?: boolean;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  language: UiLanguage;
};

type RowActionState = {
  pending: boolean;
  diagnostic: string | null;
  restartRequired: boolean;
};

function stateBadgeVariant(state: PluginLifecycleState) {
  if (state === 'enabled') return 'success' as const;
  if (state === 'failed') return 'danger' as const;
  if (state === 'disabled') return 'default' as const;
  return 'warning' as const;
}

function formatDiagnostic(result: PluginLifecycleResponse): string | null {
  const parts: string[] = [];
  if (result.errorCode) {
    parts.push(result.errorCode);
  }
  if (result.message) {
    parts.push(result.message);
  }
  if (parts.length === 0) {
    return null;
  }
  return parts.join(' — ');
}

const PluginsPanel: React.FC<PluginsPanelProps> = ({
  disabled = false,
  t,
  language,
}) => {
  const [items, setItems] = useState<PluginInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [rowState, setRowState] = useState<Record<string, RowActionState>>({});
  const [bannerRestart, setBannerRestart] = useState(false);

  const setRow = useCallback((pluginId: string, patch: Partial<RowActionState>) => {
    setRowState((prev) => {
      const current = prev[pluginId] ?? {
        pending: false,
        diagnostic: null,
        restartRequired: false,
      };
      return {
        ...prev,
        [pluginId]: { ...current, ...patch },
      };
    });
  }, []);

  const loadPlugins = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    setLoadError(null);
    if (mode === 'initial') {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }
    try {
      const response = await pluginsApi.list();
      setItems(response.items);
      setTotal(response.total);
    } catch (error: unknown) {
      setLoadError(getParsedApiError(error, language));
      setItems([]);
      setTotal(0);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [language]);

  useEffect(() => {
    void loadPlugins('initial');
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional one-shot mount load
  }, []);

  const applyLifecycleResult = useCallback((
    pluginId: string,
    result: PluginLifecycleResponse,
  ) => {
    const diagnostic = formatDiagnostic(result);
    setRow(pluginId, {
      pending: false,
      diagnostic: result.success && !result.restartRequired ? null : diagnostic,
      restartRequired: result.restartRequired,
    });
    if (result.restartRequired) {
      setBannerRestart(true);
    }
    if (result.plugin) {
      setItems((prev) => prev.map((item) => (
        item.id === pluginId ? result.plugin as PluginInfo : item
      )));
    } else if (result.success) {
      setItems((prev) => prev.map((item) => (
        item.id === pluginId
          ? {
            ...item,
            state: result.state,
            desiredEnabled: result.action === 'disable'
              ? false
              : result.action === 'enable'
                ? true
                : item.desiredEnabled,
          }
          : item
      )));
    }
  }, [setRow]);

  const runLifecycle = useCallback(async (
    pluginId: string,
    action: 'enable' | 'disable' | 'reload',
  ) => {
    setRow(pluginId, { pending: true, diagnostic: null });
    try {
      const result = await pluginsApi.updateLifecycle(pluginId, action);
      applyLifecycleResult(pluginId, result);
      if (!result.success && !result.message && !result.errorCode) {
        setRow(pluginId, {
          pending: false,
          diagnostic: t('settings.pluginsActionFailedGeneric'),
        });
      }
    } catch (error: unknown) {
      const parsed = getParsedApiError(error, language);
      setRow(pluginId, {
        pending: false,
        diagnostic: parsed.message || t('settings.pluginsActionFailedGeneric'),
        restartRequired: false,
      });
    }
  }, [applyLifecycleResult, language, setRow, t]);

  const handleToggle = (plugin: PluginInfo, nextEnabled: boolean) => {
    if (disabled || rowState[plugin.id]?.pending) {
      return;
    }
    void runLifecycle(plugin.id, nextEnabled ? 'enable' : 'disable');
  };

  const handleReload = (plugin: PluginInfo) => {
    if (disabled || rowState[plugin.id]?.pending) {
      return;
    }
    void runLifecycle(plugin.id, 'reload');
  };

  const stateLabel = (state: PluginLifecycleState): string => {
    if (state === 'enabled') return t('settings.pluginsStateEnabled');
    if (state === 'disabled') return t('settings.pluginsStateDisabled');
    if (state === 'failed') return t('settings.pluginsStateFailed');
    return t('settings.pluginsStateRegistered');
  };

  const sourceLabel = (source: PluginInfo['source']): string => {
    return source === 'builtin'
      ? t('settings.pluginsSourceBuiltin')
      : t('settings.pluginsSourceExternal');
  };

  return (
    <SettingsSectionCard
      title={t('settings.pluginsTitle')}
      description={t('settings.pluginsDescription')}
      contentBordered
      actions={(
        <IconButton
          type="button"
          variant="outline"
          size="compact"
          onClick={() => void loadPlugins('refresh')}
          disabled={disabled || isLoading || isRefreshing}
          isLoading={isRefreshing}
          aria-label={t('settings.pluginsRefresh')}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
        </IconButton>
      )}
    >
      <div
        className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm leading-6 text-foreground"
        data-testid="settings-plugins-trust-banner"
        role="note"
      >
        <p className="font-medium">{t('settings.pluginsTrustTitle')}</p>
        <p className="mt-1 text-secondary-text">{t('settings.pluginsTrustBody')}</p>
      </div>

      {bannerRestart ? (
        <div
          className="mb-4 rounded-lg border border-border bg-[var(--settings-surface)] px-3 py-2 text-sm leading-6 text-secondary-text"
          data-testid="settings-plugins-restart-banner"
          role="status"
        >
          {t('settings.pluginsRestartRequiredBanner')}
        </div>
      ) : null}

      {loadError ? (
        <div className="mb-3">
          <ApiErrorAlert error={loadError} />
        </div>
      ) : null}

      {isLoading ? (
        <StatePanel
          state="loading"
          title={t('common.loading')}
          size="compact"
          titleAs="p"
        />
      ) : null}

      {!isLoading && !loadError && items.length === 0 ? (
        <EmptyState
          compact
          title={t('settings.pluginsEmptyTitle')}
          description={t('settings.pluginsEmptyDescription')}
        />
      ) : null}

      {!isLoading && items.length > 0 ? (
        <div
          role="region"
          aria-label={t('settings.pluginsListLabel')}
          data-testid="settings-plugins-list"
          className="space-y-3"
        >
          <p className="text-xs text-muted-text">
            {t('settings.pluginsTotal', { total })}
          </p>
          {items.map((plugin) => {
            const row = rowState[plugin.id];
            const pending = Boolean(row?.pending);
            const sourcePath = plugin.packageRoot
              || (plugin.source === 'builtin'
                ? t('settings.pluginsSourcePathBuiltin')
                : t('settings.pluginsSourcePathUnknown'));
            const hooks = plugin.extensionPoints.length > 0
              ? plugin.extensionPoints.join(', ')
              : t('settings.pluginsHooksNone');
            const showFailedHint = plugin.state === 'failed';

            return (
              <article
                key={plugin.id}
                className="rounded-lg border border-border/70 bg-[var(--settings-surface)] p-3"
                data-testid={`settings-plugin-row-${plugin.id}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-foreground">
                        {plugin.name}
                      </p>
                      <Badge variant="history" size="sm">
                        v{plugin.version}
                      </Badge>
                      <Badge variant={stateBadgeVariant(plugin.state)} size="sm">
                        {stateLabel(plugin.state)}
                      </Badge>
                      <Badge variant="default" size="sm">
                        {sourceLabel(plugin.source)}
                      </Badge>
                    </div>
                    <p className="font-mono text-xs text-muted-text">
                      {plugin.id}
                    </p>
                    <dl className="grid gap-1 text-xs text-secondary-text sm:grid-cols-2">
                      <div>
                        <dt className="inline text-muted-text">
                          {t('settings.pluginsColumnHooks')}
                          {': '}
                        </dt>
                        <dd className="inline break-all font-mono">{hooks}</dd>
                      </div>
                      <div>
                        <dt className="inline text-muted-text">
                          {t('settings.pluginsColumnSourcePath')}
                          {': '}
                        </dt>
                        <dd className="inline break-all font-mono">{sourcePath}</dd>
                      </div>
                    </dl>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <SettingsSwitch
                      checked={plugin.desiredEnabled}
                      onCheckedChange={(next) => handleToggle(plugin, next)}
                      disabled={disabled || pending || isLoading}
                      aria-label={t('settings.pluginsToggleAria', { name: plugin.name })}
                      testId={`settings-plugin-toggle-${plugin.id}`}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="compact"
                      onClick={() => handleReload(plugin)}
                      disabled={disabled || pending || isLoading}
                      data-testid={`settings-plugin-reload-${plugin.id}`}
                    >
                      <RotateCcw className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                      {t('settings.pluginsReload')}
                    </Button>
                  </div>
                </div>

                {showFailedHint ? (
                  <p
                    className="mt-2 text-xs leading-5 text-danger"
                    data-testid={`settings-plugin-failed-${plugin.id}`}
                  >
                    {row?.diagnostic
                      ? t('settings.pluginsFailedWithDiagnostic', {
                        diagnostic: row.diagnostic,
                      })
                      : t('settings.pluginsFailedNoDiagnostic')}
                  </p>
                ) : null}

                {!showFailedHint && row?.diagnostic ? (
                  <p
                    className="mt-2 text-xs leading-5 text-danger"
                    data-testid={`settings-plugin-diagnostic-${plugin.id}`}
                  >
                    {row.diagnostic}
                  </p>
                ) : null}

                {row?.restartRequired ? (
                  <p
                    className="mt-2 text-xs leading-5 text-secondary-text"
                    data-testid={`settings-plugin-restart-${plugin.id}`}
                  >
                    {plugin.reloadable
                      ? t('settings.pluginsRestartRequiredPartial')
                      : t('settings.pluginsRestartRequiredBuiltin')}
                  </p>
                ) : null}

                {!plugin.reloadable && plugin.source === 'builtin' ? (
                  <p className="mt-2 text-xxs leading-5 text-muted-text">
                    {t('settings.pluginsReloadBuiltinHint')}
                  </p>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : null}
    </SettingsSectionCard>
  );
};

export default PluginsPanel;
