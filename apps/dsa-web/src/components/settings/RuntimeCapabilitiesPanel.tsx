// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useMemo, useState } from 'react';
import { agentApi, type AgentModelDeployment } from '../../api/agent';
import {
  capabilitiesApi,
  type CapabilityItem,
  type CapabilityListResponse,
  type CapabilitySourceStatus,
} from '../../api/capabilities';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { MODEL_ACCESS_TEXT } from '../../locales/settingsModelAccess';
import { SETTINGS_PAGE_TEXT } from '../../locales/settingsPage';
import {
  Badge,
  Button,
  DataTable,
  SummaryStrip,
  type DataTableColumn,
} from '../common';
import { SettingsAlert } from './SettingsAlert';
import { viewLabel } from './settingsInformationArchitecture';
import { SettingsSectionCard } from './SettingsSectionCard';

type CapabilityTone = 'success' | 'warning' | 'danger' | 'default';

function capabilityState(
  item: CapabilityItem,
  labels: {
    executable: string;
    unavailable: string;
    degraded: string;
    unknown: string;
  },
): { label: string; variant: CapabilityTone } {
  if (item.degraded) return { label: labels.degraded, variant: 'warning' };
  if (item.executable === true) return { label: labels.executable, variant: 'success' };
  if (item.executable === false) return { label: labels.unavailable, variant: 'danger' };
  return { label: labels.unknown, variant: 'default' };
}

function sourceTone(source: CapabilitySourceStatus): CapabilityTone {
  if (source.state === 'ok') return 'success';
  if (source.state === 'error') return 'danger';
  return 'warning';
}

function sourceStateLabel(
  source: CapabilitySourceStatus,
  labels: {
    executable: string;
    unavailable: string;
    degraded: string;
    unknown: string;
  },
): string {
  if (source.state === 'ok') return labels.executable;
  if (source.state === 'error') return labels.unavailable;
  if (source.state === 'generation_drift') return labels.degraded;
  return labels.unknown;
}

export function RuntimeCapabilitiesPanel() {
  const { language } = useUiLanguage();
  const text = SETTINGS_PAGE_TEXT[language];
  const modelText = MODEL_ACCESS_TEXT[language];
  const capabilityTitle = viewLabel('advanced', 'capabilities', language);
  const agentModelsTitle = `${text.routeAgent} · ${modelText.availableModels}`;
  const capabilityReloadLabel = `${text.reload}: ${capabilityTitle}`;
  const modelReloadLabel = `${text.reload}: ${agentModelsTitle}`;
  const [capabilities, setCapabilities] = useState<CapabilityListResponse | null>(null);
  const [models, setModels] = useState<AgentModelDeployment[] | null>(null);
  const [capabilitiesError, setCapabilitiesError] = useState<ParsedApiError | null>(null);
  const [modelsError, setModelsError] = useState<ParsedApiError | null>(null);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(true);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [capabilitiesRequest, setCapabilitiesRequest] = useState(0);
  const [modelsRequest, setModelsRequest] = useState(0);

  const reloadCapabilities = useCallback(() => {
    setCapabilitiesLoading(true);
    setCapabilitiesError(null);
    setCapabilitiesRequest((request) => request + 1);
  }, []);

  const reloadModels = useCallback(() => {
    setModelsLoading(true);
    setModelsError(null);
    setModelsRequest((request) => request + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void capabilitiesApi.list().then((response) => {
      if (cancelled) return;
      setCapabilities(response);
      setCapabilitiesError(null);
    }).catch((error: unknown) => {
      if (cancelled) return;
      setCapabilitiesError(getParsedApiError(error));
    }).finally(() => {
      if (!cancelled) setCapabilitiesLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [capabilitiesRequest]);

  useEffect(() => {
    let cancelled = false;
    void agentApi.getModels().then((response) => {
      if (cancelled) return;
      setModels(response.models);
      setModelsError(null);
    }).catch((error: unknown) => {
      if (cancelled) return;
      setModelsError(getParsedApiError(error));
    }).finally(() => {
      if (!cancelled) setModelsLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [modelsRequest]);

  const capabilityRows = useMemo(
    () => [...(capabilities?.items ?? [])].sort((left, right) => (
      left.domain.localeCompare(right.domain) || left.id.localeCompare(right.id)
    )),
    [capabilities],
  );

  const capabilityColumns = useMemo<readonly DataTableColumn<CapabilityItem>[]>(() => [
    {
      id: 'id',
      header: capabilityTitle,
      rowHeader: true,
      cell: (item) => (
        <div className="min-w-0">
          <p className="break-words font-medium text-foreground">{item.display_name || item.id}</p>
          <p className="mt-0.5 break-all font-mono text-xxs text-muted-text">{item.id}</p>
        </div>
      ),
    },
    {
      id: 'owner',
      header: text.runtimeCapabilitiesOwnerProvider,
      cell: (item) => (
        <div className="min-w-0 text-secondary-text">
          <p className="break-all">{item.owner}</p>
          <p className="mt-0.5 break-all text-xxs text-muted-text">{item.provider}</p>
        </div>
      ),
    },
    {
      id: 'runtime',
      header: text.runtimeCapabilitiesRuntimeColumn,
      cell: (item) => {
        const state = capabilityState(item, {
          executable: text.runtimeCapabilitiesExecutable,
          unavailable: text.runtimeCapabilitiesUnavailable,
          degraded: text.runtimeCapabilitiesDegraded,
          unknown: text.runtimeCapabilitiesUnknown,
        });
        return (
          <div className="min-w-0">
            <Badge variant={state.variant}>{state.label}</Badge>
            {item.reason_code ? (
              <p className="mt-1 break-all text-xxs text-muted-text">{item.reason_code}</p>
            ) : null}
          </div>
        );
      },
    },
  ], [capabilityTitle, text]);

  const modelColumns = useMemo<readonly DataTableColumn<AgentModelDeployment>[]>(() => [
    {
      id: 'deployment',
      header: text.runtimeCapabilitiesDeployment,
      rowHeader: true,
      cell: (model) => (
        <div className="min-w-0">
          <p className="break-all font-medium text-foreground">
            {model.deployment_name || model.deployment_id}
          </p>
          <p className="mt-0.5 break-all font-mono text-xxs text-muted-text">{model.deployment_id}</p>
        </div>
      ),
    },
    {
      id: 'model',
      header: text.runtimeCapabilitiesModel,
      cell: (model) => <span className="break-all text-secondary-text">{model.model}</span>,
    },
    {
      id: 'source',
      header: text.runtimeCapabilitiesProviderSource,
      cell: (model) => (
        <div className="min-w-0 text-secondary-text">
          <p className="break-all">{model.provider}</p>
          <p className="mt-0.5 break-all text-xxs text-muted-text">{model.source}</p>
        </div>
      ),
    },
    {
      id: 'role',
      header: text.runtimeCapabilitiesRole,
      cell: (model) => (
        <div className="flex flex-wrap gap-1">
          {model.is_primary ? <Badge variant="success">{text.runtimeCapabilitiesPrimary}</Badge> : null}
          {model.is_fallback ? <Badge variant="warning">{text.runtimeCapabilitiesFallback}</Badge> : null}
          {!model.is_primary && !model.is_fallback ? (
            <Badge>{text.runtimeCapabilitiesRuntime}</Badge>
          ) : null}
        </div>
      ),
    },
  ], [text]);

  const capabilityRetry = (
    <Button variant="secondary" size="default" onClick={reloadCapabilities}>
      {text.reload}
    </Button>
  );
  const modelRetry = (
    <Button variant="secondary" size="default" onClick={reloadModels}>
      {text.reload}
    </Button>
  );

  return (
    <div className="min-w-0 space-y-4" data-testid="runtime-capabilities-panel">
      <SettingsSectionCard
        title={capabilityTitle}
        actions={(
          <div className="flex items-center gap-2">
            {capabilities?.partial ? (
              <Badge variant="warning">{text.runtimeCapabilitiesPartial}</Badge>
            ) : null}
            <Button
              variant="outline"
              size="default"
              aria-label={capabilityReloadLabel}
              isLoading={capabilitiesLoading}
              onClick={reloadCapabilities}
            >
              {text.reload}
            </Button>
          </div>
        )}
      >
        {capabilities ? (
          <SummaryStrip
            aria-label={capabilityTitle}
            items={[
              { id: 'total', label: capabilityTitle, value: capabilities.total },
              {
                id: 'executable',
                label: text.runtimeCapabilitiesExecutable,
                value: capabilities.executable_count,
                tone: 'success',
              },
              {
                id: 'unavailable',
                label: text.runtimeCapabilitiesUnavailable,
                value: capabilities.non_executable_count,
                tone: capabilities.non_executable_count > 0 ? 'danger' : 'default',
              },
              {
                id: 'unknown',
                label: text.runtimeCapabilitiesUnknown,
                value: capabilities.unknown_executable_count,
                tone: capabilities.unknown_executable_count > 0 ? 'warning' : 'default',
              },
            ]}
          />
        ) : null}
        {capabilitiesError && capabilities ? (
          <SettingsAlert
            title={capabilitiesError.title}
            message={capabilitiesError.message}
            actionLabel={text.reload}
            onAction={reloadCapabilities}
          />
        ) : null}
        {capabilities?.sources?.length ? (
          <div className="flex flex-wrap gap-2" aria-label={text.runtimeCapabilitiesSources}>
            {capabilities.sources.map((source) => (
              <Badge
                key={source.source}
                variant={sourceTone(source)}
                title={source.error_code || undefined}
              >
                {source.source}: {sourceStateLabel(source, {
                  executable: text.runtimeCapabilitiesExecutable,
                  unavailable: text.runtimeCapabilitiesUnavailable,
                  degraded: text.runtimeCapabilitiesDegraded,
                  unknown: text.runtimeCapabilitiesUnknown,
                })}
              </Badge>
            ))}
          </div>
        ) : null}
        <DataTable
          caption={capabilityTitle}
          scrollAreaLabel={capabilityTitle}
          columns={capabilityColumns}
          rows={capabilityRows}
          getRowKey={(item) => item.id}
          density="compact"
          frame="embedded"
          minWidth="content"
          virtualization={false}
          emptyState={{ title: `${capabilityTitle}: 0` }}
          status={capabilitiesLoading && !capabilities
            ? { state: 'loading', title: capabilityTitle }
            : capabilitiesError && !capabilities
              ? {
                  state: 'error',
                  title: capabilitiesError.title,
                  description: capabilitiesError.message,
                  action: capabilityRetry,
                }
              : undefined}
        />
      </SettingsSectionCard>

      <SettingsSectionCard
        title={agentModelsTitle}
        actions={(
          <Button
            variant="outline"
            size="default"
            aria-label={modelReloadLabel}
            isLoading={modelsLoading}
            onClick={reloadModels}
          >
            {text.reload}
          </Button>
        )}
      >
        {modelsError && models ? (
          <SettingsAlert
            title={modelsError.title}
            message={modelsError.message}
            actionLabel={text.reload}
            onAction={reloadModels}
          />
        ) : null}
        <DataTable
          caption={agentModelsTitle}
          scrollAreaLabel={agentModelsTitle}
          columns={modelColumns}
          rows={models ?? []}
          getRowKey={(model) => model.deployment_id}
          density="compact"
          frame="embedded"
          minWidth="content"
          virtualization={false}
          emptyState={{ title: text.noModels }}
          status={modelsLoading && !models
            ? { state: 'loading', title: agentModelsTitle }
            : modelsError && !models
              ? {
                  state: 'error',
                  title: modelsError.title,
                  description: modelsError.message,
                  action: modelRetry,
                }
              : undefined}
        />
      </SettingsSectionCard>
    </div>
  );
}
