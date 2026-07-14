import type { AvailableModelEntry, LlmProviderCatalogEntry } from '../../types/systemConfig';

export type ConnectionStatus = 'configured' | 'incomplete' | 'disabled';

export interface ConnectionCard {
  /** Internal connection name (the LLM_CHANNELS entry). Not shown as "channel". */
  name: string;
  /** Provider id from the catalog, or the raw name when unknown. */
  providerId: string;
  /** User-facing provider label. */
  providerLabel: string;
  protocol: string;
  enabled: boolean;
  status: ConnectionStatus;
  modelCount: number;
  models: string[];
  /** Task labels (report / agent / vision / fallback) that use this connection. */
  usedByTasks: string[];
}

interface DeriveInput {
  /** Effective config values, keyed by UPPERCASE key. */
  valuesByKey: Record<string, string>;
  providers: LlmProviderCatalogEntry[];
  availableModels: AvailableModelEntry[];
  /** Task label → the route currently assigned to that task. */
  taskAssignments: Array<{ label: string; route: string }>;
}

function parseBool(value: string | undefined): boolean {
  if (value === undefined || value === '') {
    return true; // channels default to enabled
  }
  return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
}

function splitList(value: string | undefined): string[] {
  return (value ?? '')
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
}

/**
 * Derive the "model access" service cards from the current config, provider
 * catalog and the authoritative available-model routes. Pure/testable: no I/O.
 */
export function deriveConnections(input: DeriveInput): ConnectionCard[] {
  const { valuesByKey, providers, availableModels, taskAssignments } = input;
  const providerById = new Map(providers.map((provider) => [provider.id, provider]));
  const providerByProtocol = new Map(providers.map((provider) => [provider.protocol, provider]));
  // route -> connection name (authoritative grouping).
  const connectionByRoute = new Map(
    availableModels.filter((model) => model.connection).map((model) => [model.route, model.connection as string]),
  );

  const names = splitList(valuesByKey.LLM_CHANNELS);
  return names.map((name) => {
    const prefix = `LLM_${name.toUpperCase()}`;
    const enabled = parseBool(valuesByKey[`${prefix}_ENABLED`]);
    const protocol = (valuesByKey[`${prefix}_PROTOCOL`] || '').trim() || 'openai';
    const models = splitList(valuesByKey[`${prefix}_MODELS`]);
    const apiKey = (valuesByKey[`${prefix}_API_KEY`] || valuesByKey[`${prefix}_API_KEYS`] || '').trim();
    const baseUrl = (valuesByKey[`${prefix}_BASE_URL`] || '').trim();

    const provider = providerById.get(name.toLowerCase()) ?? providerByProtocol.get(protocol);
    const providerLabel = provider?.label ?? name;
    const localHost = /^(https?:\/\/)?(127\.0\.0\.1|localhost|0\.0\.0\.0)(:|\/|$)/.test(baseUrl);
    const keyExempt = protocol === 'ollama' || localHost || provider?.requiresApiKey === false;

    let status: ConnectionStatus;
    if (!enabled) {
      status = 'disabled';
    } else if (models.length === 0 || (!keyExempt && !apiKey)) {
      status = 'incomplete';
    } else {
      status = 'configured';
    }

    const usedByTasks = taskAssignments
      .filter((task) => task.route && connectionByRoute.get(task.route) === name)
      .map((task) => task.label);

    return {
      name,
      providerId: provider?.id ?? name,
      providerLabel,
      protocol,
      enabled,
      status,
      modelCount: models.length,
      models,
      usedByTasks,
    };
  });
}
