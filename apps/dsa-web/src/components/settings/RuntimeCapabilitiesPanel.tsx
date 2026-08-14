// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { agentApi, type AgentModelDeployment } from '../../api/agent';
import {
  capabilitiesApi,
  type CapabilityItem,
  type CapabilityListResponse,
} from '../../api/capabilities';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { MODEL_ACCESS_TEXT } from '../../locales/settingsModelAccess';
import { SETTINGS_PAGE_TEXT } from '../../locales/settingsPage';
import { Badge, Button, DataTable, type DataTableColumn } from '../common';
import { viewLabel } from './settingsInformationArchitecture';
import { SettingsSectionCard } from './SettingsSectionCard';

function capabilityState(
  item: CapabilityItem,
  labels: {
    executable: string;
    unavailable: string;
    degraded: string;
    unknown: string;
  },
): {
  label: string;
  variant: 'success' | 'warning' | 'danger' | 'default';
} {
  if (item.executable === true) return { label: labels.executable, variant: 'success' };
  if (item.executable === false) {
    return { label: item.reason_code || labels.unavailable, variant: 'danger' };
  }
  if (item.degraded) return { label: item.reason_code || labels.degraded, variant: 'warning' };
  return { label: item.reason_code || labels.unknown, variant: 'default' };
}

export function RuntimeCapabilitiesPanel() {
  const { language } = useUiLanguage();
  const settingsText = SETTINGS_PAGE_TEXT[language];
  const modelText = MODEL_ACCESS_TEXT[language];
  const capabilityTitle = viewLabel('advanced', 'capabilities', language);
  const agentModelsTitle = `${settingsText.routeAgent} · ${modelText.availableModels}`;
  const [capabilities, setCapabilities] = useState<CapabilityListResponse | null>(null);
  const [models, setModels] = useState<AgentModelDeployment[]>([]);
  const [capabilitiesError, setCapabilitiesError] = useState<ParsedApiError | null>(null);
  const [modelsError, setModelsError] = useState<ParsedApiError | null>(null);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(true);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [reloadToken, setReloadToken] = useState(0);

  const reload = useCallback(() => {
    setCapabilitiesLoading(true);
    setModelsLoading(true);
    setCapabilitiesError(null);
    setModelsError(null);
    setReloadToken((token) => token + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;

    void capabilitiesApi.list().then((response) => {
      if (cancelled) return;
      setCapabilities(response);
    }).catch((error: unknown) => {
      if (cancelled) return;
      setCapabilities(null);
      setCapabilitiesError(getParsedApiError(error));
    }).finally(() => {
      if (!cancelled) setCapabilitiesLoading(false);
    });

    void agentApi.getModels().then((response) => {
      if (cancelled) return;
      setModels(response.models);
    }).catch((error: unknown) => {
      if (cancelled) return;
      setModels([]);
      setModelsError(getParsedApiError(error));
    }).finally(() => {
      if (!cancelled) setModelsLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const capabilityRows = useMemo(
    () => [...(capabilities?.items ?? [])].sort((left, right) => (
      left.domain.localeCompare(right.domain) || left.id.localeCompare(right.id)
    )),
    [capabilities],
  );

  const capabilityColumns = useMemo<readonly DataTableColumn<CapabilityItem>[]>(() => [
    {
      id: 'id',
      header: 'ID',
      rowHeader: true,
      cell: (item) => (
        <div className="min-w-0">
          <p className="font-medium text-foreground break-words">{item.display_name || item.id}</p>
          <p className="mt-0.5 font-mono text-xxs text-muted-text break-all">{item.id}</p>
        </div>
      ),
    },
    {
      id: 'owner',
      header: settingsText.runtimeCapabilitiesOwnerProvider,
      cell: (item) => (
        <div className="min-w-0 text-secondary-text">
          <p className="break-all">{item.owner}</p>
          <p className="mt-0.5 text-xxs text-muted-text break-all">{item.provider}</p>
        </div>
      ),
    },
    {
      id: 'runtime',
      header: settingsText.runtimeCapabilitiesRuntimeColumn,
      nowrap: true,
      cell: (item) => {
        const state = capabilityState(item, {
          executable: settingsText.runtimeCapabilitiesExecutable,
          unavailable: settingsText.runtimeCapabilitiesUnavailable,
          degraded: settingsText.runtimeCapabilitiesDegraded,
          unknown: settingsText.runtimeCapabilitiesUnknown,
        });
        return <Badge variant={state.variant}>{state.label}</Badge>;
      },
    },
  ], [settingsText]);

  const modelColumns = useMemo<readonly DataTableColumn<AgentModelDeployment>[]>(() => [
    {
      id: 'deployment',
      header: settingsText.runtimeCapabilitiesDeployment,
      rowHeader: true,
      cell: (model) => (
        <div className="min-w-0">
          <p className="font-medium text-foreground break-all">
            {model.deployment_name || model.deployment_id}
          </p>
          <p className="mt-0.5 font-mono text-xxs text-muted-text break-all">{model.deployment_id}</p>
        </div>
      ),
    },
    {
      id: 'model',
      header: settingsText.runtimeCapabilitiesModel,
      cell: (model) => <span className="break-all text-secondary-text">{model.model}</span>,
    },
    {
      id: 'source',
      header: settingsText.runtimeCapabilitiesProviderSource,
      cell: (model) => (
        <div className="min-w-0 text-secondary-text">
          <p className="break-all">{model.provider}</p>
          <p className="mt-0.5 text-xxs text-muted-text break-all">{model.source}</p>
        </div>
      ),
    },
    {
      id: 'role',
      header: settingsText.runtimeCapabilitiesRole,
      nowrap: true,
      cell: (model) => (
        <div className="flex flex-wrap gap-1">
          {model.is_primary ? <Badge variant="success">{settingsText.runtimeCapabilitiesPrimary}</Badge> : null}
          {model.is_fallback ? <Badge variant="warning">{settingsText.runtimeCapabilitiesFallback}</Badge> : null}
          {!model.is_primary && !model.is_fallback ? <Badge>{settingsText.runtimeCapabilitiesRuntime}</Badge> : null}
        </div>
      ),
    },
  ], [settingsText]);

  const retryAction = (
    <Button variant="secondary" size="default" onClick={reload}>
      <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
      {settingsText.reload}
    </Button>
  );

  return (
    <div className="space-y-4" data-testid="runtime-capabilities-panel">
      <SettingsSectionCard
        title={capabilityTitle}
        actions={(
          <div className="flex items-center gap-2">
            {capabilities?.partial ? <Badge variant="warning">{settingsText.runtimeCapabilitiesPartial}</Badge> : null}
            {retryAction}
          </div>
        )}
      >
        {capabilities?.sources?.length ? (
          <div className="flex flex-wrap gap-2" aria-label={settingsText.runtimeCapabilitiesSources}>
            {capabilities.sources.map((source) => (
              <Badge key={source.source} variant={source.state === 'ok' ? 'success' : 'warning'}>
                {source.source}: {source.state}
              </Badge>
            ))}
          </div>
        ) : null}
        <DataTable
          caption={capabilityTitle}
          columns={capabilityColumns}
          rows={capabilityRows}
          getRowKey={(item) => item.id}
          density="compact"
          minWidth="content"
          emptyState={{ title: `${capabilityTitle}: 0` }}
          status={capabilitiesLoading
            ? { state: 'loading', title: capabilityTitle }
            : capabilitiesError
              ? { state: 'error', title: capabilitiesError.title, description: capabilitiesError.message, action: retryAction }
              : undefined}
        />
      </SettingsSectionCard>

      <SettingsSectionCard title={agentModelsTitle}>
        <DataTable
          caption={agentModelsTitle}
          columns={modelColumns}
          rows={models}
          getRowKey={(model) => model.deployment_id}
          density="compact"
          minWidth="content"
          emptyState={{ title: settingsText.noModels }}
          status={modelsLoading
            ? { state: 'loading', title: agentModelsTitle }
            : modelsError
              ? { state: 'error', title: modelsError.title, description: modelsError.message, action: retryAction }
              : undefined}
        />
      </SettingsSectionCard>
    </div>
  );
}
