import { getParsedApiError } from '../../api/error';
import { systemConfigApi } from '../../api/systemConfig';
import type {
  AvailableModelEntry,
  LLMCapabilityCheck,
  LLMCapabilityCheckResult,
  LlmConnectionFieldSchema,
  LlmProviderCatalogEntry,
} from '../../types/systemConfig';
import { formatUiText, type UiLanguage } from '../../i18n/uiText';
import {
  MODEL_ACCESS_EDITOR_TEXT,
  MODEL_ACCESS_ERROR_LABELS,
  MODEL_ACCESS_REASON_HINTS,
  MODEL_ACCESS_STAGE_LABELS,
  MODEL_ACCESS_TEXT,
  MODEL_ACCESS_TROUBLESHOOTING,
} from '../../locales/settingsModelAccess';
import {
  canonicalModelRoute,
  buildConnectionContractValues,
  type ConnectionCredentialField,
  type ConnectionSchemaAuthority,
  connectionAllowsEmptyApiKey,
  evaluateConnectionSchemaAuthority,
  isConnectionSchemaFieldWritable,
  validateConnectionContractValues,
} from './llmConnectionContract';
import type { ChannelProtocol } from './llmProviderTemplates';
import {
  CHANNEL_FIELD_KEY_PATTERN,
  CHANNEL_FIELD_SUFFIXES,
  CONNECTION_SCHEMA_KEY_BY_SUFFIX,
  SUPPORTED_CONNECTION_SCHEMA_KEYS,
  parseModelAccessFieldKey,
  type ModelAccessFieldFocusRequest,
} from '../../utils/modelAccessFieldKey';
import { encodeModelRef, isModelRef } from '../../utils/modelRef';
import { getUiColon } from '../../utils/uiLocale';

export function findCatalogProvider(
  providers: LlmProviderCatalogEntry[],
  id: string,
): LlmProviderCatalogEntry | undefined {
  return providers.find((provider) => provider.id === id);
}

function isKnownCatalogProvider(providers: LlmProviderCatalogEntry[], id: string): boolean {
  return id !== 'custom' && providers.some((provider) => provider.id === id);
}

// During an initial catalog outage, an existing explicit non-Custom Provider
// id is the only provider contract we can safely preserve. This does not infer
// any business metadata or enable new connections; it only prevents a saved
// official connection from being reinterpreted as Custom while metadata is
// temporarily unavailable.
export function preservesUnavailableProviderSnapshot(
  providers: LlmProviderCatalogEntry[],
  providerId: string,
  catalogUnavailable: boolean,
): boolean {
  const normalizedId = providerId.trim().toLowerCase();
  return catalogUnavailable
    && normalizedId.length > 0
    && normalizedId !== 'custom'
    && !findCatalogProvider(providers, normalizedId);
}
const FALSEY_VALUES = new Set(['0', 'false', 'no', 'off']);
const HERMES_CHANNEL_NAME = 'hermes';
const HERMES_DEFAULT_MODEL = 'hermes-agent';
export const CONNECTION_SCHEMA_UNAVAILABLE_ISSUE = '连接 Schema 不完整或不可用';
export const CONNECTION_SCHEMA_UNKNOWN_CONDITION_ISSUE = '连接字段契约包含不支持的条件';

export const isHermesChannel = (channel: Pick<ChannelConfig, 'name'>): boolean => (
  channel.name.trim().toLowerCase() === HERMES_CHANNEL_NAME
);

export function canonicalizeHermesRouteModel(model: string): string {
  const trimmed = model.trim() || HERMES_DEFAULT_MODEL;
  return trimmed.startsWith('openai/') ? trimmed : `openai/${trimmed}`;
}

export const shouldUseSavedHermesSecret = (
  channel: Pick<ChannelConfig, 'name' | 'apiKey'>,
  maskToken: string,
  hasPersistedSecret: boolean,
): boolean => (
  isHermesChannel(channel) && channel.apiKey === maskToken && hasPersistedSecret
);

export const hasRuntimeOnlyMaskedHermesSecret = (
  channel: Pick<ChannelConfig, 'name' | 'apiKey'>,
  maskToken: string,
  hasPersistedSecret: boolean,
): boolean => (
  isHermesChannel(channel) && channel.apiKey === maskToken && !hasPersistedSecret
);

export interface ChannelConfig {
  id: string;
  /** Stable runtime identity used in env keys and ModelRef values. */
  name: string;
  /** User-facing label; changing it never changes the Connection identity. */
  displayName: string;
  /** The card may show a fallback label without making it a Schema value. */
  displayNameValuePresent: boolean;
  providerId: string;
  /** False when the persisted Provider identity is absent. */
  providerIdExplicit: boolean;
  protocol: ChannelProtocol;
  /** Distinguishes a persisted protocol from the legacy UI fallback. */
  protocolValuePresent: boolean;
  baseUrl: string;
  apiKey: string;
  /** Schema field that owns apiKey, independent of how many keys it contains. */
  credentialField: ConnectionCredentialField;
  models: string;
  extraHeaders: string;
  enabled: boolean;
  /** A persisted false is a value; an absent boolean is not. */
  enabledValuePresent: boolean;
}

export interface ChannelTestState {
  status: 'idle' | 'loading' | 'success' | 'error';
  text?: string;
  hint?: string;
}

/** Primitive inputs for a connectivity check shared by the editor and wizard. */
export interface LlmConnectionCheckInput {
  name: string;
  providerId: string;
  protocol: string;
  baseUrl?: string;
  apiKey?: string;
  models: string[];
  enabled?: boolean;
  useSavedSecret?: boolean;
  capabilityChecks?: LLMCapabilityCheck[];
}

/**
 * Full connectivity-test outcome. Extends the editor's `ChannelTestState`
 * presentation (status/text/hint) with the resolved effective configuration and
 * per-capability results so callers can surface transparent diagnostics.
 */
export interface LlmConnectionCheckOutcome {
  status: 'success' | 'error';
  text: string;
  hint?: string;
  resolvedModel?: string | null;
  resolvedProtocol?: string | null;
  latencyMs?: number | null;
  capabilityResults?: Partial<Record<LLMCapabilityCheck, LLMCapabilityCheckResult>>;
}

/** Localized label for a capability check, reusing the shared stage labels. */
export function getLlmCapabilityLabel(
  capability: LLMCapabilityCheck,
  language: UiLanguage,
): string {
  return MODEL_ACCESS_STAGE_LABELS[language][`capability_${capability}`] || capability;
}

export interface ChannelDiscoveryState {
  status: 'idle' | 'loading' | 'success' | 'error';
  text?: string;
  hint?: string;
  models: string[];
}

interface RuntimeConfig {
  primaryModel: string;
  agentPrimaryModel: string;
  fallbackModels: string[];
  visionModel: string;
  temperature: string;
}

export interface TaskModelReference {
  key?: string;
  label: string;
  route: string;
}

export interface ModelReferenceReplacement {
  fromRoute: string;
  toRoute: string;
  references: TaskModelReference[];
}

export interface LLMChannelEditorProps {
  items: Array<{ key: string; value: string; rawValueExists?: boolean }>;
  /** Authoritative provider catalog (business metadata) from the backend. */
  providers: LlmProviderCatalogEntry[];
  /** Dynamic field behavior from the same backend Catalog response. */
  connectionFields?: LlmConnectionFieldSchema[];
  /** Hosts the backend exempts from API-key requirements (local endpoints). */
  emptyApiKeyHosts?: string[];
  /** Authoritative routes, used for backend-equivalent historical Agent normalization. */
  availableModelRoutes?: string[];
  /** Connection-aware identities returned by Available Models. */
  availableModels?: AvailableModelEntry[];
  maskToken: string;
  /** Parent-held channel draft, used to rehydrate after a tab-switch remount. */
  persistedDraftItems?: Array<{ key: string; value: string }>;
  onDraftItemsChange?: (items: Array<{ key: string; value: string }>) => void;
  /** Reports whether the current draft passes the structural completeness gate. */
  onValidityChange?: (valid: boolean) => void;
  /** Bumped by the parent to discard the local draft back to the saved snapshot. */
  resetSignal?: number;
  /** Bumped by the parent to open the "add connection" dialog. */
  addSignal?: number;
  /** Opens the owning connection dialog and focuses a dynamic backend field. */
  focusFieldRequest?: ModelAccessFieldFocusRequest | null;
  disabled?: boolean;
  /** True until the Catalog response establishes schema-present vs legacy. */
  catalogLoading?: boolean;
  /**
   * The provider catalog failed to load. Existing connections stay editable/
   * read-only, but adding a NEW connection is blocked so we never create a
   * blank custom-like connection from a transient catalog outage.
   */
  catalogUnavailable?: boolean;
  /** Retry loading the provider catalog after a failure. */
  onReloadCatalog?: () => void;
  /** When a non-channels config source is effective, the editor is read-only. */
  overriddenByMode?: 'yaml' | 'legacy' | null;
  /** Jump to the developer diagnostics area for details on the config source. */
  onViewDiagnostics?: () => void;
  /** Task -> route references, to show which tasks use each connection. */
  taskModelRefs?: TaskModelReference[];
  /** Jump to the task-routing view to assign models to tasks. */
  onManageModels?: () => void;
  /** Replace task references in the parent-owned unified draft as one batch. */
  onReplaceModelReferences?: (replacements: ModelReferenceReplacement[]) => void;
}

function parseChannelFieldKeys(channel: ChannelConfig): string[] {
  const upperName = channel.name.trim().toUpperCase();
  return [
    `LLM_${upperName}_DISPLAY_NAME`,
    `LLM_${upperName}_PROVIDER`,
    `LLM_${upperName}_PROTOCOL`,
    `LLM_${upperName}_BASE_URL`,
    `LLM_${upperName}_ENABLED`,
    `LLM_${upperName}_API_KEY`,
    `LLM_${upperName}_API_KEYS`,
    `LLM_${upperName}_MODELS`,
    `LLM_${upperName}_EXTRA_HEADERS`,
  ];
}

function parseChannelFieldKeysFromName(name: string): string[] {
  const upperName = name.trim().toUpperCase();
  return CHANNEL_FIELD_SUFFIXES.map((suffix) => `LLM_${upperName}_${suffix}`);
}

function isChannelSecretFieldKey(key: string): boolean {
  const match = CHANNEL_FIELD_KEY_PATTERN.exec(key.toUpperCase());
  return match?.[2] === 'API_KEY' || match?.[2] === 'API_KEYS';
}

export const CONNECTION_FIELD_BY_DRAFT_KEY: Partial<Record<keyof ChannelConfig, string>> = {
  name: 'connection_name',
  displayName: 'display_name',
  protocol: 'protocol',
  baseUrl: 'base_url',
  models: 'models',
  extraHeaders: 'extra_headers',
  enabled: 'enabled',
};

function resolveInitialChannelApiKeySource(
  channelName: string,
  initialItemValueByKey: Map<string, string>,
  initialItemSourceByKey: Map<string, boolean>,
): boolean | undefined {
  const upperName = channelName.trim().toUpperCase();
  const apiKeysKey = `LLM_${upperName}_API_KEYS`;
  const apiKeyKey = `LLM_${upperName}_API_KEY`;

  const apiKeysValue = (initialItemValueByKey.get(apiKeysKey) || '').trim();
  const apiKeyValue = (initialItemValueByKey.get(apiKeyKey) || '').trim();

  if (channelName.trim().toLowerCase() === HERMES_CHANNEL_NAME && apiKeyValue && initialItemSourceByKey.has(apiKeyKey)) {
    return initialItemSourceByKey.get(apiKeyKey);
  }
  if (apiKeysValue && initialItemSourceByKey.has(apiKeysKey)) {
    return initialItemSourceByKey.get(apiKeysKey);
  }
  if (apiKeyValue && initialItemSourceByKey.has(apiKeyKey)) {
    return initialItemSourceByKey.get(apiKeyKey);
  }

  if (apiKeyValue) {
    return initialItemSourceByKey.get(apiKeyKey);
  }
  if (apiKeysValue) {
    return initialItemSourceByKey.get(apiKeysKey);
  }
  return initialItemSourceByKey.get(apiKeysKey) ?? initialItemSourceByKey.get(apiKeyKey);
}

function resolveInitialChannelApiKeyValue(
  channelName: string,
  itemValueByKey: Map<string, string>,
  itemSourceByKey: Map<string, boolean>,
): string {
  const upperName = channelName.trim().toUpperCase();
  const apiKeysKey = `LLM_${upperName}_API_KEYS`;
  const apiKeyKey = `LLM_${upperName}_API_KEY`;

  const apiKeysValue = (itemValueByKey.get(apiKeysKey) || '').trim();
  const apiKeyValue = (itemValueByKey.get(apiKeyKey) || '').trim();

  if (channelName.trim().toLowerCase() === HERMES_CHANNEL_NAME && apiKeyValue) {
    return apiKeyValue;
  }
  if (apiKeysValue && itemSourceByKey.has(apiKeysKey)) {
    return apiKeysValue;
  }
  if (apiKeyValue && itemSourceByKey.has(apiKeyKey)) {
    return apiKeyValue;
  }
  if (apiKeysValue) {
    return apiKeysValue;
  }
  if (apiKeyValue) {
    return apiKeyValue;
  }
  return itemValueByKey.get(apiKeysKey) || itemValueByKey.get(apiKeyKey) || '';
}

function resolveInitialChannelCredentialField(
  channelName: string,
  itemValueByKey: Map<string, string>,
): ConnectionCredentialField {
  const upperName = channelName.trim().toUpperCase();
  const apiKeysValue = (itemValueByKey.get(`LLM_${upperName}_API_KEYS`) || '').trim();
  const apiKeyValue = (itemValueByKey.get(`LLM_${upperName}_API_KEY`) || '').trim();
  if (channelName.trim().toLowerCase() === HERMES_CHANNEL_NAME) {
    return 'api_key';
  }
  if (apiKeysValue || (!apiKeyValue && itemValueByKey.has(`LLM_${upperName}_API_KEYS`))) {
    return 'api_keys';
  }
  // Preserve the legacy editor's comma-to-API_KEYS behavior when an old
  // single-key field happens to contain a list.
  return apiKeyValue.split(',').filter((segment) => segment.trim()).length > 1
    ? 'api_keys'
    : 'api_key';
}

function buildChangedItemKeys(
  channels: ChannelConfig[],
  initialChannels: ChannelConfig[],
  initialItemSourceByKey: Map<string, boolean>,
  initialItemValueByKey: Map<string, string>,
): Set<string> {
  const changedKeys = new Set<string>();
  const nextChannelNames = channels.map((channel) => channel.name.trim().toLowerCase()).join(',');
  const previousChannelNames = initialChannels.map((channel) => channel.name.trim().toLowerCase()).join(',');

  if (nextChannelNames !== previousChannelNames) {
    changedKeys.add('LLM_CHANNELS');
  }

  const maxLength = Math.max(channels.length, initialChannels.length);
  for (let index = 0; index < maxLength; index += 1) {
    const current = channels[index];
    const previous = initialChannels[index];
    if (!current && !previous) {
      continue;
    }

    if (!current) {
      const previousKeys = parseChannelFieldKeys(previous);
      for (const key of previousKeys) {
        if (initialItemSourceByKey.get(key.toUpperCase()) !== false) {
          changedKeys.add(key);
        }
      }
      continue;
    }

    if (!previous) {
      for (const key of parseChannelFieldKeys(current)) {
        changedKeys.add(key);
      }
      continue;
    }

    const currentName = current.name.trim().toUpperCase();
    const previousName = previous.name.trim().toUpperCase();
    if (currentName !== previousName) {
      const previousApiKeySource = resolveInitialChannelApiKeySource(
        previous.name,
        initialItemValueByKey,
        initialItemSourceByKey,
      );
      const preserveRuntimeOnlySecret = previousApiKeySource === false && current.apiKey === previous.apiKey;
      const previousKeys = parseChannelFieldKeys(previous);
      for (const key of previousKeys) {
        if (initialItemSourceByKey.get(key.toUpperCase()) !== false) {
          changedKeys.add(key);
        }
      }

      for (const key of parseChannelFieldKeys(current)) {
        if (preserveRuntimeOnlySecret && isChannelSecretFieldKey(key)) {
          continue;
        }
        changedKeys.add(key);
      }
      continue;
    }

    const prefix = `LLM_${currentName}`;
    if (
      current.displayName !== previous.displayName
      || current.displayNameValuePresent !== previous.displayNameValuePresent
    ) {
      changedKeys.add(`${prefix}_DISPLAY_NAME`);
    }
    if (
      current.protocol !== previous.protocol
      || current.protocolValuePresent !== previous.protocolValuePresent
    ) {
      changedKeys.add(`${prefix}_PROTOCOL`);
    }
    if (
      current.providerId !== previous.providerId
      || current.providerIdExplicit !== previous.providerIdExplicit
    ) {
      changedKeys.add(`${prefix}_PROVIDER`);
    }
    if (current.baseUrl !== previous.baseUrl) {
      changedKeys.add(`${prefix}_BASE_URL`);
    }
    if (
      current.enabled !== previous.enabled
      || current.enabledValuePresent !== previous.enabledValuePresent
    ) {
      changedKeys.add(`${prefix}_ENABLED`);
    }
    if (
      current.apiKey !== previous.apiKey
      || current.credentialField !== previous.credentialField
    ) {
      changedKeys.add(`${prefix}_API_KEY`);
      changedKeys.add(`${prefix}_API_KEYS`);
    }
    if (current.models !== previous.models) {
      changedKeys.add(`${prefix}_MODELS`);
    }
    if (current.extraHeaders !== previous.extraHeaders) {
      changedKeys.add(`${prefix}_EXTRA_HEADERS`);
    }
  }

  return changedKeys;
}

// Backward compatibility for configurations created before explicit provider
// identity existed. Only an exact catalog-id match is reliable; prefixes such as
// "openai2" can also be user-chosen Custom names and must not be guessed.
function inferLegacyProviderId(
  providers: LlmProviderCatalogEntry[],
  name: string,
): string {
  const lower = name.trim().toLowerCase();
  return providers.find((provider) => provider.id !== 'custom' && provider.id.toLowerCase() === lower)?.id
    ?? 'custom';
}

function resolveConnectionContractProvider(
  channel: ChannelConfig,
  providers: LlmProviderCatalogEntry[],
): LlmProviderCatalogEntry | undefined {
  const provider = findCatalogProvider(providers, channel.providerId);
  if (channel.providerIdExplicit || !provider?.isCustom) {
    return provider;
  }
  return providers.find((entry) => (
    entry.isLocal
    && normalizeProtocol(entry.protocol) === normalizeProtocol(channel.protocol)
  )) ?? provider;
}

export function buildChannelContractValues(
  channel: ChannelConfig,
  providers: LlmProviderCatalogEntry[],
  emptyApiKeyHosts: string[],
  options: { baseUrlVisible?: boolean; extraHeadersVisible?: boolean } = {},
): Record<string, string> {
  const values = buildConnectionContractValues({
    connectionName: channel.name,
    displayName: channel.displayName,
    providerId: channel.providerId,
    provider: resolveConnectionContractProvider(channel, providers),
    protocol: channel.protocol,
    baseUrl: channel.baseUrl,
    apiKey: channel.apiKey,
    credentialField: channel.credentialField,
    models: channel.models,
    extraHeaders: channel.extraHeaders,
    enabled: channel.enabled,
    emptyApiKeyHosts,
    ...options,
  });
  if (!channel.displayNameValuePresent) {
    values.display_name = '';
  }
  if (!channel.providerIdExplicit) {
    values.provider_id = '';
  }
  if (!channel.protocolValuePresent) {
    values.protocol = '';
  }
  if (!channel.enabledValuePresent) {
    values.enabled = '';
  }
  return values;
}

export function evaluateChannelSchemaAuthority(
  channel: ChannelConfig,
  providers: LlmProviderCatalogEntry[],
  emptyApiKeyHosts: string[],
  connectionFields?: LlmConnectionFieldSchema[],
  options: { baseUrlVisible?: boolean; extraHeadersVisible?: boolean } = {},
): ConnectionSchemaAuthority {
  return evaluateConnectionSchemaAuthority(
    buildChannelContractValues(channel, providers, emptyApiKeyHosts, options),
    connectionFields,
  );
}

export function channelSchemaAllowsKnownOperations(
  channel: ChannelConfig,
  providers: LlmProviderCatalogEntry[],
  emptyApiKeyHosts: string[],
  connectionFields?: LlmConnectionFieldSchema[],
): boolean {
  return evaluateChannelSchemaAuthority(
    channel,
    providers,
    emptyApiKeyHosts,
    connectionFields,
  ).usable;
}

export function channelIdentityCanWrite(
  channel: ChannelConfig,
  providers: LlmProviderCatalogEntry[],
  emptyApiKeyHosts: string[],
  connectionFields?: LlmConnectionFieldSchema[],
): boolean {
  const authority = evaluateChannelSchemaAuthority(
    channel,
    providers,
    emptyApiKeyHosts,
    connectionFields,
  );
  return authority.usable
    && isConnectionSchemaFieldWritable(authority, 'connection_name')
    && isConnectionSchemaFieldWritable(authority, 'provider_id');
}

export function channelConnectionNameCanWrite(
  channel: ChannelConfig,
  providers: LlmProviderCatalogEntry[],
  emptyApiKeyHosts: string[],
  connectionFields?: LlmConnectionFieldSchema[],
): boolean {
  const authority = evaluateChannelSchemaAuthority(
    channel,
    providers,
    emptyApiKeyHosts,
    connectionFields,
  );
  return authority.usable
    && isConnectionSchemaFieldWritable(authority, 'connection_name');
}

export function channelFieldCanWrite(
  channel: ChannelConfig,
  key: string,
  providers: LlmProviderCatalogEntry[],
  emptyApiKeyHosts: string[],
  connectionFields?: LlmConnectionFieldSchema[],
): boolean {
  const authority = evaluateChannelSchemaAuthority(
    channel,
    providers,
    emptyApiKeyHosts,
    connectionFields,
  );
  return isConnectionSchemaFieldWritable(authority, key);
}

export function countChannelsForProvider(
  channels: ChannelConfig[],
  providerId: string,
): number {
  return channels.filter((channel) => channel.providerId === providerId).length;
}

export function describeProviderOption(entry: LlmProviderCatalogEntry, connectedCount: number, language: UiLanguage): string {
  const text = MODEL_ACCESS_TEXT[language];
  const protocol = normalizeProtocol(entry.protocol);
  const protocolLabel = formatProtocolLabel(protocol);
  const purpose = entry.isLocal
    ? text.localPurpose
    : entry.isCustom
      ? text.customPurpose
      : entry.capabilities.includes('aggregator')
        ? text.aggregatorPurpose
        : text.cloudPurpose;
  return `${protocolLabel} · ${purpose}${connectedCount > 0 ? ` · ${formatUiText(text.connectedCount, { count: connectedCount })}` : ''}`;
}

// Shared connectivity-test runner. Both the editor and the first-run wizard call
// it so failure diagnostics, resolved config, and capability results stay
// consistent. Callers that want capability checks pass `capabilityChecks`; the
// backend runs them only after a successful base test and never lets them flip
// the overall connectivity verdict.
export async function runLlmConnectionCheck(
  input: LlmConnectionCheckInput,
  language: UiLanguage,
): Promise<LlmConnectionCheckOutcome> {
  const text = MODEL_ACCESS_TEXT[language];
  try {
    const result = await systemConfigApi.testLLMChannel({
      name: input.name,
      providerId: input.providerId,
      protocol: input.protocol,
      baseUrl: input.baseUrl,
      apiKey: input.apiKey,
      models: input.models,
      enabled: input.enabled,
      useSavedSecret: input.useSavedSecret,
      capabilityChecks: input.capabilityChecks,
    });
    if (result.success) {
      return {
        status: 'success',
        text: `${text.connectionSucceeded}${result.resolvedModel ? ` · ${result.resolvedModel}` : ''}${result.latencyMs ? ` · ${result.latencyMs} ms` : ''}`,
        resolvedModel: result.resolvedModel ?? null,
        resolvedProtocol: result.resolvedProtocol ?? null,
        latencyMs: result.latencyMs ?? null,
        capabilityResults: result.capabilityResults,
      };
    }
    return {
      status: 'error',
      text: buildLlmFailureText(result, language),
      hint: buildLlmTestHint(result, language),
      resolvedModel: result.resolvedModel ?? null,
      resolvedProtocol: result.resolvedProtocol ?? null,
      capabilityResults: result.capabilityResults,
    };
  } catch (error: unknown) {
    const parsed = getParsedApiError(error, language);
    return { status: 'error', text: parsed.message || text.testFailed };
  }
}

// Shared connectivity-test runner used by the card quick action and the
// connection dialog (the dialog must keep failures inline without closing).
export async function runChannelConnectionTest(
  channel: ChannelConfig,
  useSavedSecret: boolean,
  language: UiLanguage,
): Promise<ChannelTestState> {
  const outcome = await runLlmConnectionCheck({
    name: channel.name,
    providerId: channel.providerId,
    protocol: channel.protocol,
    baseUrl: channel.baseUrl,
    apiKey: channel.apiKey,
    models: splitModels(channel.models),
    enabled: channel.enabled,
    useSavedSecret,
  }, language);
  return { status: outcome.status, text: outcome.text, hint: outcome.hint };
}

// Shared model-discovery runner. A successful call with an empty list is a
// distinct outcome (endpoint reachable but no model IDs) — not an error.
export async function runChannelModelDiscovery(
  channel: ChannelConfig,
  useSavedSecret: boolean,
  language: UiLanguage,
): Promise<ChannelDiscoveryState> {
  const text = MODEL_ACCESS_TEXT[language];
  try {
    const result = await systemConfigApi.discoverLLMChannelModels({
      name: channel.name,
      providerId: channel.providerId,
      protocol: channel.protocol,
      baseUrl: channel.baseUrl,
      apiKey: channel.apiKey,
      models: splitModels(channel.models),
      useSavedSecret,
    });
    if (result.success) {
      if (result.models.length === 0) {
        return {
          status: 'success',
          text: text.noDiscoveredModels,
          hint: text.noDiscoveredModelsHint,
          models: [],
        };
      }
      return {
        status: 'success',
        text: `${formatUiText(text.discoveredModels, { count: result.models.length })}${result.latencyMs ? ` · ${result.latencyMs} ms` : ''}`,
        models: result.models,
      };
    }
    return {
      status: 'error',
      text: buildLlmFailureText(result, language),
      hint: getLlmTroubleshootingHint(result.errorCode, result.stage, 'discovery', result.details, language),
      models: [],
    };
  } catch (error: unknown) {
    const parsed = getParsedApiError(error, language);
    return { status: 'error', text: parsed.message || text.discoveryFailed, models: [] };
  }
}
export function normalizeProtocol(value: string): ChannelProtocol {
  const normalized = value.trim().toLowerCase().replace(/-/g, '_');
  if (normalized === 'vertex' || normalized === 'vertexai') {
    return 'vertex_ai';
  }
  if (normalized === 'claude') {
    return 'anthropic';
  }
  if (normalized === 'google') {
    return 'gemini';
  }
  if (normalized === 'deepseek') {
    return 'deepseek';
  }
  if (normalized === 'gemini') {
    return 'gemini';
  }
  if (normalized === 'anthropic') {
    return 'anthropic';
  }
  if (normalized === 'vertex_ai') {
    return 'vertex_ai';
  }
  if (normalized === 'ollama') {
    return 'ollama';
  }
  return 'openai';
}

export function formatProtocolLabel(protocol: string): string {
  return protocol
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
    .replace('Openai', 'OpenAI');
}

export function buildProtocolOptions(
  providers: LlmProviderCatalogEntry[],
  currentProtocol: ChannelProtocol | undefined,
): Array<{ value: ChannelProtocol; label: string }> {
  const values = new Set<ChannelProtocol>();
  for (const provider of providers) {
    values.add(normalizeProtocol(provider.protocol));
  }
  if (currentProtocol) {
    values.add(currentProtocol);
  }
  return Array.from(values).map((value) => ({
    value,
    label: formatProtocolLabel(value),
  }));
}

function inferProtocol(protocol: string, baseUrl: string, models: string[]): ChannelProtocol {
  const explicit = normalizeProtocol(protocol);
  if (protocol.trim()) {
    return explicit;
  }

  const firstPrefixedModel = models.find((model) => model.includes('/'));
  if (firstPrefixedModel) {
    return normalizeProtocol(firstPrefixedModel.split('/', 1)[0]);
  }

  if (baseUrl.includes('127.0.0.1') || baseUrl.includes('localhost')) {
    return 'openai';
  }

  return 'openai';
}

function parseEnabled(value: string | undefined): boolean {
  if (!value) {
    return true;
  }
  return !FALSEY_VALUES.has(value.trim().toLowerCase());
}

export function splitModels(models: string): string[] {
  return models
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
}

interface ParsedModelRef {
  name: string;
  provider: string;
  hasProvider: boolean;
}

function parseModelRef(model: string): ParsedModelRef {
  const trimmed = model.trim();
  if (!trimmed) {
    return { name: '', provider: '', hasProvider: false };
  }

  const delimiterIndex = trimmed.indexOf('/');
  if (delimiterIndex < 0) {
    return { name: trimmed.toLowerCase(), provider: '', hasProvider: false };
  }

  const rawProvider = trimmed.slice(0, delimiterIndex).trim();
  const name = trimmed.slice(delimiterIndex + 1).trim();
  if (!rawProvider || !name) {
    return { name: '', provider: '', hasProvider: false };
  }

  const lowerProvider = rawProvider.toLowerCase();
  return {
    name: name.toLowerCase(),
    provider: PROTOCOL_ALIASES[lowerProvider] || lowerProvider,
    hasProvider: true,
  };
}

function getModelComparisonKey(model: string, protocol: ChannelProtocol): string {
  const normalizedModel = normalizeModelForRuntime(model, protocol).trim();
  const parsed = parseModelRef(normalizedModel);
  if (!parsed.name) {
    return '';
  }
  return `${parsed.provider}/${parsed.name}`;
}

export function areModelsEquivalent(a: string, b: string, protocol: ChannelProtocol): boolean {
  const left = getModelComparisonKey(a, protocol);
  const right = getModelComparisonKey(b, protocol);
  return left !== '' && left === right;
}

export function toggleModelSelection(models: string, targetModel: string, protocol: ChannelProtocol): string {
  const selectedModels = splitModels(models);
  const index = selectedModels.findIndex((model) => areModelsEquivalent(model, targetModel, protocol));
  if (index >= 0) {
    return selectedModels.filter((_, itemIndex) => itemIndex !== index).join(',');
  }
  return [...selectedModels, targetModel].join(',');
}

const PROTOCOL_ALIASES: Record<string, string> = {
  vertexai: 'vertex_ai',
  vertex: 'vertex_ai',
  claude: 'anthropic',
  google: 'gemini',
  openai_compatible: 'openai',
  openai_compat: 'openai',
};

export function normalizeModelForRuntime(model: string, protocol: ChannelProtocol): string {
  return canonicalModelRoute(protocol, model);
}

function resolveModelPreview(models: string, protocol: ChannelProtocol): string[] {
  return splitModels(models).map((model) => normalizeModelForRuntime(model, protocol));
}

export function resolveChannelRouteModels(channel: ChannelConfig): string[] {
  if (isHermesChannel(channel)) {
    const models = splitModels(channel.models);
    return (models.length > 0 ? models : [HERMES_DEFAULT_MODEL]).map(canonicalizeHermesRouteModel);
  }
  return resolveModelPreview(channel.models, channel.protocol);
}

export function collectChannelRouteSet(channels: ChannelConfig[], enabledOnly: boolean): Set<string> {
  const routes = new Set<string>();
  for (const channel of channels) {
    if (enabledOnly && !channel.enabled) {
      continue;
    }
    for (const route of resolveChannelRouteModels(channel)) {
      if (route) {
        routes.add(route);
      }
    }
  }
  return routes;
}

export function modelIdentityForConnection(
  availableModels: AvailableModelEntry[],
  connectionId: string,
  runtimeRoute: string,
): string {
  return availableModels.find((entry) => (
    entry.connectionId?.toLowerCase() === connectionId.trim().toLowerCase()
    && entry.route === runtimeRoute
  ))?.modelRef ?? encodeModelRef(connectionId, runtimeRoute);
}

// Mirrors normalize_agent_litellm_model() in the backend. Other task fields
// use exact route identity; only the historical Agent field accepts a bare
// model name and resolves it against the currently configured routes first.
export function normalizeTaskReferenceRoute(
  reference: TaskModelReference,
  knownRoutes: Set<string>,
): string {
  const route = reference.route.trim();
  if (!route || isModelRef(route) || reference.key !== 'AGENT_LITELLM_MODEL' || route.includes('/')) {
    return route;
  }
  return knownRoutes.has(route) ? route : `openai/${route}`;
}

function getLlmStageLabel(stage: string | null | undefined, language: UiLanguage): string {
  return MODEL_ACCESS_STAGE_LABELS[language][stage || ''] || MODEL_ACCESS_EDITOR_TEXT[language].connectionTest;
}

function getLlmErrorCodeLabel(code: string | null | undefined, language: UiLanguage): string {
  return MODEL_ACCESS_ERROR_LABELS[language][code || ''] || MODEL_ACCESS_TEXT[language].testFailed;
}

function getLlmTroubleshootingHint(
  code?: string | null,
  stage?: string | null,
  context: 'test' | 'discovery' = 'test',
  details?: Record<string, unknown>,
  language: UiLanguage = 'zh',
): string | undefined {
  const reason = typeof details?.reason === 'string' ? details.reason : '';
  if (reason && MODEL_ACCESS_REASON_HINTS[language][reason]) {
    return MODEL_ACCESS_REASON_HINTS[language][reason];
  }
  if (code === 'format_error') {
    return context === 'discovery' || stage === 'model_discovery'
      ? MODEL_ACCESS_EDITOR_TEXT[language].discoveryFormatHint
      : MODEL_ACCESS_EDITOR_TEXT[language].completionFormatHint;
  }
  if (code === 'empty_response' && (context === 'discovery' || stage === 'model_discovery')) {
    return MODEL_ACCESS_EDITOR_TEXT[language].discoveryEmptyHint;
  }
  return MODEL_ACCESS_TROUBLESHOOTING[language][code || ''];
}

function buildLlmTestHint(result: {
  errorCode?: string | null;
  stage?: string | null;
  details?: Record<string, unknown>;
  resolvedModel?: string | null;
}, language: UiLanguage): string | undefined {
  const text = MODEL_ACCESS_EDITOR_TEXT[language];
  const reason = typeof result.details?.reason === 'string' ? result.details.reason : '';
  const detailsModel = typeof result.details?.model === 'string' ? result.details.model : '';
  const testedModel = result.resolvedModel || detailsModel;
  const modelHint = testedModel ? formatUiText(text.testedModel, { model: testedModel }) : '';
  const scopeInfo = text.firstModelOnly;
  const shouldSuggestModelListChange = reason === 'model_access_denied'
    || reason === 'model_not_found'
    || (result.errorCode === 'model_not_found' && !reason);
  const modelActionHint = shouldSuggestModelListChange
    ? text.adjustModelList
    : '';
  const troubleshootingHint = getLlmTroubleshootingHint(result.errorCode, result.stage, 'test', result.details, language);
  return [modelHint, scopeInfo, modelActionHint, troubleshootingHint].filter(Boolean).join(' ') || undefined;
}

function buildLlmFailureText(result: {
  message: string;
  error?: string | null;
  stage?: string | null;
  errorCode?: string | null;
}, language: UiLanguage): string {
  const editorText = MODEL_ACCESS_EDITOR_TEXT[language];
  const prefix = `${getLlmStageLabel(result.stage, language)} · ${getLlmErrorCodeLabel(result.errorCode, language)}`;
  const summary = language === 'zh'
    ? result.message || MODEL_ACCESS_TEXT[language].testFailed
    : getLlmErrorCodeLabel(result.errorCode, language);
  if (language === 'zh' && result.error && result.error !== result.message) {
    return `${prefix}：${summary} (${formatUiText(editorText.rawSummary, { summary: result.error })})`;
  }
  return `${prefix}${getUiColon(language)}${summary}`;
}

function runtimeConfigChangedKeys(left: RuntimeConfig, right: RuntimeConfig): Set<string> {
  const changed = new Set<string>();
  if (left.primaryModel !== right.primaryModel) {
    changed.add('LITELLM_MODEL');
  }
  if (left.agentPrimaryModel !== right.agentPrimaryModel) {
    changed.add('AGENT_LITELLM_MODEL');
  }
  if (left.fallbackModels.join(',') !== right.fallbackModels.join(',')) {
    changed.add('LITELLM_FALLBACK_MODELS');
  }
  if (left.temperature !== right.temperature) {
    changed.add('LLM_TEMPERATURE');
  }
  if (left.visionModel !== right.visionModel) {
    changed.add('VISION_MODEL');
  }
  return changed;
}

function resolveTemperatureFromItems(itemMap: Map<string, string>): string {
  const unified = itemMap.get('LLM_TEMPERATURE');
  if (unified) return unified;

  const primaryModel = itemMap.get('LITELLM_MODEL') || '';
  const provider = primaryModel.includes('/') ? primaryModel.split('/')[0] : (primaryModel ? 'openai' : '');
  const providerTemperatureEnv: Record<string, string> = {
    gemini: 'GEMINI_TEMPERATURE',
    vertex_ai: 'GEMINI_TEMPERATURE',
    anthropic: 'ANTHROPIC_TEMPERATURE',
    openai: 'OPENAI_TEMPERATURE',
    deepseek: 'OPENAI_TEMPERATURE',
  };
  const preferredEnv = providerTemperatureEnv[provider];
  if (preferredEnv) {
    const val = itemMap.get(preferredEnv);
    if (val) return val;
  }

  for (const envName of ['GEMINI_TEMPERATURE', 'ANTHROPIC_TEMPERATURE', 'OPENAI_TEMPERATURE']) {
    const val = itemMap.get(envName);
    if (val) return val;
  }

  return '0.7';
}

function normalizeAgentPrimaryModel(model: string): string {
  const trimmedModel = model.trim();
  if (!trimmedModel) {
    return '';
  }
  if (trimmedModel.includes('/')) {
    return trimmedModel;
  }
  return `openai/${trimmedModel}`;
}

export function parseRuntimeConfigFromItems(items: Array<{ key: string; value: string }>): RuntimeConfig {
  const itemMap = new Map(items.map((item) => [item.key, item.value]));
  return {
    primaryModel: itemMap.get('LITELLM_MODEL') || '',
    agentPrimaryModel: normalizeAgentPrimaryModel(itemMap.get('AGENT_LITELLM_MODEL') || ''),
    fallbackModels: splitModels(itemMap.get('LITELLM_FALLBACK_MODELS') || ''),
    visionModel: itemMap.get('VISION_MODEL') || '',
    temperature: resolveTemperatureFromItems(itemMap),
  };
}

export function parseChannelsFromItems(
  items: Array<{ key: string; value: string }>,
  itemSourceByKey: Map<string, boolean> = new Map(),
  providers: LlmProviderCatalogEntry[] = [],
  connectionFields?: LlmConnectionFieldSchema[],
): ChannelConfig[] {
  const itemMap = new Map(items.map((item) => [item.key.toUpperCase(), item.value]));
  const channelNames = (itemMap.get('LLM_CHANNELS') || '')
    .split(',')
    .map((segment) => segment.trim())
    .filter(Boolean);

  return channelNames.map((name, index) => {
    const upperName = name.toUpperCase();
    const legacyMode = connectionFields === undefined;
    const displayNameKey = `LLM_${upperName}_DISPLAY_NAME`;
    const providerKey = `LLM_${upperName}_PROVIDER`;
    const protocolKey = `LLM_${upperName}_PROTOCOL`;
    const enabledKey = `LLM_${upperName}_ENABLED`;
    const fieldHasSource = (key: string) => (
      itemMap.has(key) && itemSourceByKey.get(key) !== false
    );
    const baseUrl = itemMap.get(`LLM_${upperName}_BASE_URL`) || '';
    const rawModels = itemMap.get(`LLM_${upperName}_MODELS`) || '';
    const models = splitModels(rawModels);
    const explicitProviderId = fieldHasSource(providerKey)
      ? (itemMap.get(providerKey) || '').trim().toLowerCase()
      : '';
    const rawProtocol = fieldHasSource(protocolKey) ? (itemMap.get(protocolKey) || '') : '';
    const rawEnabled = fieldHasSource(enabledKey) ? itemMap.get(enabledKey) : undefined;

    return {
      id: `parsed:${index}:${upperName}`,
      name: name.toLowerCase(),
      displayName: fieldHasSource(displayNameKey)
        ? (itemMap.get(displayNameKey) ?? '')
        : name,
      displayNameValuePresent: fieldHasSource(displayNameKey) || legacyMode,
      providerId: explicitProviderId || inferLegacyProviderId(providers, name),
      providerIdExplicit: Boolean(explicitProviderId),
      protocol: inferProtocol(rawProtocol, baseUrl, models),
      protocolValuePresent: Boolean(rawProtocol.trim()) || legacyMode,
      baseUrl,
      apiKey: resolveInitialChannelApiKeyValue(name, itemMap, itemSourceByKey),
      credentialField: resolveInitialChannelCredentialField(name, itemMap),
      models: rawModels,
      extraHeaders: itemMap.get(`LLM_${upperName}_EXTRA_HEADERS`) || '',
      enabled: parseEnabled(rawEnabled),
      enabledValuePresent: Boolean(rawEnabled?.trim()) || legacyMode,
    };
  });
}

function channelsToUpdateItems(
  channels: ChannelConfig[],
  previousChannelNames: string[],
  runtimeConfig: RuntimeConfig,
  includeRuntimeConfig: boolean,
): Array<{ key: string; value: string }> {
  const updates: Array<{ key: string; value: string }> = [];
  const activeNames = channels.map((channel) => channel.name.toUpperCase());

  updates.push({ key: 'LLM_CHANNELS', value: channels.map((channel) => channel.name).join(',') });
  if (includeRuntimeConfig) {
    updates.push({ key: 'LITELLM_MODEL', value: runtimeConfig.primaryModel });
    updates.push({ key: 'AGENT_LITELLM_MODEL', value: runtimeConfig.agentPrimaryModel });
    updates.push({ key: 'LITELLM_FALLBACK_MODELS', value: runtimeConfig.fallbackModels.join(',') });
    updates.push({ key: 'VISION_MODEL', value: runtimeConfig.visionModel });
    updates.push({ key: 'LLM_TEMPERATURE', value: runtimeConfig.temperature });
  }

  for (const channel of channels) {
    const prefix = `LLM_${channel.name.toUpperCase()}`;
    updates.push({ key: `${prefix}_DISPLAY_NAME`, value: channel.displayName.trim() });
    updates.push({ key: `${prefix}_PROVIDER`, value: channel.providerId });
    updates.push({ key: `${prefix}_PROTOCOL`, value: channel.protocol });
    updates.push({ key: `${prefix}_BASE_URL`, value: channel.baseUrl });
    updates.push({ key: `${prefix}_ENABLED`, value: channel.enabled ? 'true' : 'false' });
    if (isHermesChannel(channel)) {
      updates.push({ key: `${prefix}_API_KEY`, value: channel.apiKey });
      updates.push({ key: `${prefix}_API_KEYS`, value: '' });
    } else {
      const credentialSuffix = channel.credentialField === 'api_keys' ? 'API_KEYS' : 'API_KEY';
      const siblingSuffix = channel.credentialField === 'api_keys' ? 'API_KEY' : 'API_KEYS';
      updates.push({ key: `${prefix}_${credentialSuffix}`, value: channel.apiKey });
      updates.push({ key: `${prefix}_${siblingSuffix}`, value: '' });
    }
    updates.push({ key: `${prefix}_MODELS`, value: channel.models });
    updates.push({ key: `${prefix}_EXTRA_HEADERS`, value: channel.extraHeaders });
  }

  for (const oldName of previousChannelNames) {
    const upperName = oldName.toUpperCase();
    if (activeNames.includes(upperName)) {
      continue;
    }

    const prefix = `LLM_${upperName}`;
    updates.push({ key: `${prefix}_DISPLAY_NAME`, value: '' });
    updates.push({ key: `${prefix}_PROVIDER`, value: '' });
    updates.push({ key: `${prefix}_PROTOCOL`, value: '' });
    updates.push({ key: `${prefix}_BASE_URL`, value: '' });
    updates.push({ key: `${prefix}_ENABLED`, value: '' });
    updates.push({ key: `${prefix}_API_KEY`, value: '' });
    updates.push({ key: `${prefix}_API_KEYS`, value: '' });
    updates.push({ key: `${prefix}_MODELS`, value: '' });
    updates.push({ key: `${prefix}_EXTRA_HEADERS`, value: '' });
  }

  return updates;
}

function channelNamesAreSafe(channels: ChannelConfig[]): boolean {
  return channels.every((channel) => /^[a-z0-9_]+$/.test(channel.name.trim()));
}

// Structural completeness contract (Slice 1). Name/protocol must be valid for
// any channel; credential / base URL / models are required only when the
// channel is enabled. Connectivity testing is intentionally NOT a gate here.
export function getChannelNameIssues(channel: ChannelConfig): string[] {
  const name = channel.name.trim();
  if (!name) {
    return ['连接名称必填'];
  }
  if (!/^[a-z0-9_]+$/.test(name)) {
    return ['连接名称仅限小写字母、数字或下划线'];
  }
  return [];
}

export function getChannelDisplayNameIssues(
  channel: ChannelConfig,
  connectionFields?: LlmConnectionFieldSchema[],
): string[] {
  // Older Catalog payloads have no dynamic schema, so preserve their display
  // name requirement. Once a schema is present, its contract is authoritative.
  return connectionFields !== undefined || channel.displayName.trim()
    ? []
    : ['连接名称必填'];
}

// Mirrors the backend `channel_allows_empty_api_key` contract: ollama never
// needs a key, and OpenAI-compatible endpoints on a backend-exempted local
// host (emptyApiKeyHosts) may leave it empty too.
export function channelAllowsEmptyApiKey(
  channel: Pick<ChannelConfig, 'protocol' | 'baseUrl'>,
  emptyApiKeyHosts: string[],
): boolean {
  return connectionAllowsEmptyApiKey(channel.protocol, channel.baseUrl, emptyApiKeyHosts);
}

// Fields required to run the channel; surfaced as incomplete while missing.
export function getChannelCompletenessIssues(
  channel: ChannelConfig,
  providers: LlmProviderCatalogEntry[],
  emptyApiKeyHosts: string[],
  connectionFields?: LlmConnectionFieldSchema[],
  catalogUnavailable = false,
): string[] {
  if (connectionFields !== undefined) {
    const connectionSchemaFields = connectionFields ?? [];
    const values = buildChannelContractValues(channel, providers, emptyApiKeyHosts);
    const authority = evaluateConnectionSchemaAuthority(values, connectionSchemaFields);
    if (!authority.usable) {
      return [authority.reason === 'unknown_condition'
        ? CONNECTION_SCHEMA_UNKNOWN_CONDITION_ISSUE
        : CONNECTION_SCHEMA_UNAVAILABLE_ISSUE];
    }
    const issueByField: Record<string, string> = {
      connection_name: '连接名称必填',
      display_name: '连接名称必填',
      provider_id: '缺少模型服务商',
      protocol: '缺少连接协议',
      base_url: '缺少服务地址',
      api_key: '缺少 API 密钥',
      api_keys: '缺少 API 密钥',
      models: '至少配置一个模型',
      extra_headers: '附加请求头必填',
      enabled: '缺少启用状态',
    };
    const missingFields = validateConnectionContractValues(values, connectionSchemaFields);
    if (missingFields.some((field) => !SUPPORTED_CONNECTION_SCHEMA_KEYS.has(field))) {
      return [CONNECTION_SCHEMA_UNAVAILABLE_ISSUE];
    }
    const issues = missingFields.map(
      (field) => issueByField[field] ?? CONNECTION_SCHEMA_UNAVAILABLE_ISSUE,
    );
    return Array.from(new Set(issues));
  }

  // Rolling-upgrade compatibility for an older Catalog payload. Requirement
  // flags still come from that payload; no Provider ID table is reconstructed.
  const issues: string[] = [];
  if (!channelAllowsEmptyApiKey(channel, emptyApiKeyHosts) && !channel.apiKey.trim()) {
    issues.push('缺少 API 密钥');
  }
  // Known providers ship a default Base URL, and ollama/local endpoints have a
  // runtime default, so only custom remote endpoints must supply one. (The
  // backend completeness contract remains authoritative on save.)
  if (
    !isKnownCatalogProvider(providers, channel.providerId)
    && !preservesUnavailableProviderSnapshot(providers, channel.providerId, catalogUnavailable)
    && channel.protocol !== 'ollama'
    && !channel.baseUrl.trim()
  ) {
    issues.push('缺少服务地址');
  }
  if (splitModels(channel.models).length === 0) {
    issues.push('至少配置一个模型');
  }
  return issues;
}

// Issues that block saving: names must always be valid; enabled channels must
// additionally be complete. Disabled channels may be saved as drafts.
export function getChannelSaveIssues(
  channel: ChannelConfig,
  providers: LlmProviderCatalogEntry[],
  emptyApiKeyHosts: string[],
  connectionFields?: LlmConnectionFieldSchema[],
  catalogUnavailable = false,
): string[] {
  const nameIssues = getChannelNameIssues(channel);
  const displayNameIssues = getChannelDisplayNameIssues(channel, connectionFields);
  if (nameIssues.length > 0 || displayNameIssues.length > 0) {
    return [...nameIssues, ...displayNameIssues];
  }
  if (connectionFields !== undefined) {
    return getChannelCompletenessIssues(
      channel,
      providers,
      emptyApiKeyHosts,
      connectionFields,
      catalogUnavailable,
    );
  }
  return channel.enabled
    ? getChannelCompletenessIssues(
      channel,
      providers,
      emptyApiKeyHosts,
      connectionFields,
      catalogUnavailable,
    )
    : [];
}

function buildFilteredChannelUpdateItems({
  channels,
  initialChannels,
  initialNames,
  initialItemSourceByKey,
  savedItemMap,
  runtimeConfig,
  initialRuntimeConfig,
  managesRuntimeConfig,
  providers,
  emptyApiKeyHosts,
  connectionFields,
}: {
  channels: ChannelConfig[];
  initialChannels: ChannelConfig[];
  initialNames: string[];
  initialItemSourceByKey: Map<string, boolean>;
  savedItemMap: Map<string, string>;
  runtimeConfig: RuntimeConfig;
  initialRuntimeConfig: RuntimeConfig;
  managesRuntimeConfig: boolean;
  providers: LlmProviderCatalogEntry[];
  emptyApiKeyHosts: string[];
  connectionFields?: LlmConnectionFieldSchema[];
}): Array<{ key: string; value: string }> {
  const changedKeys = new Set<string>([
    ...buildChangedItemKeys(channels, initialChannels, initialItemSourceByKey, savedItemMap),
    ...runtimeConfigChangedKeys(runtimeConfig, initialRuntimeConfig),
  ]);
  const currentChannelsByName = new Map(
    channels.map((channel) => [channel.name.trim().toLowerCase(), channel]),
  );
  const initialChannelsByName = new Map(
    initialChannels.map((channel) => [channel.name.trim().toLowerCase(), channel]),
  );
  const schemaAllowsChannelField = (channel: ChannelConfig, fieldKey: string) => {
    const authority = evaluateChannelSchemaAuthority(
      channel,
      providers,
      emptyApiKeyHosts,
      connectionFields,
    );
    return isConnectionSchemaFieldWritable(authority, fieldKey);
  };
  const schemaAllowsItem = (itemKey: string) => {
    if (connectionFields === undefined) {
      return true;
    }
    if (itemKey === 'LLM_CHANNELS') {
      if (!changedKeys.has(itemKey)) {
        return false;
      }
      return [...currentChannelsByName.values(), ...initialChannelsByName.values()]
        .every((channel) => schemaAllowsChannelField(channel, 'connection_name'));
    }
    const parsed = parseModelAccessFieldKey(itemKey);
    if (!parsed) {
      return true;
    }
    const channel = currentChannelsByName.get(parsed.connectionName)
      ?? initialChannelsByName.get(parsed.connectionName);
    return Boolean(
      channel
      && schemaAllowsChannelField(channel, CONNECTION_SCHEMA_KEY_BY_SUFFIX[parsed.suffix]),
    );
  };

  return channelsToUpdateItems(channels, initialNames, runtimeConfig, managesRuntimeConfig).filter((item) => {
    const itemKey = item.key.toUpperCase();
    if (!schemaAllowsItem(itemKey)) {
      return false;
    }
    const initialItemSource = initialItemSourceByKey.get(itemKey);
    if (isChannelSecretFieldKey(itemKey)) {
      return changedKeys.has(itemKey);
    }
    if (
      connectionFields !== undefined
      && initialItemSource === undefined
      && !changedKeys.has(itemKey)
    ) {
      return false;
    }
    if (initialItemSource === false) {
      return changedKeys.has(itemKey);
    }
    return true;
  });
}

export function buildChannelDraftItems({
  hasChanges,
  channels,
  initialChannels,
  initialNames,
  initialItemSourceByKey,
  savedItemMap,
  runtimeConfig,
  initialRuntimeConfig,
  managesRuntimeConfig,
  providers,
  emptyApiKeyHosts,
  connectionFields,
}: {
  hasChanges: boolean;
  channels: ChannelConfig[];
  initialChannels: ChannelConfig[];
  initialNames: string[];
  initialItemSourceByKey: Map<string, boolean>;
  savedItemMap: Map<string, string>;
  runtimeConfig: RuntimeConfig;
  initialRuntimeConfig: RuntimeConfig;
  managesRuntimeConfig: boolean;
  providers: LlmProviderCatalogEntry[];
  emptyApiKeyHosts: string[];
  connectionFields?: LlmConnectionFieldSchema[];
}): Array<{ key: string; value: string }> {
  if (!hasChanges || !channelNamesAreSafe(channels)) {
    return [];
  }
  return buildFilteredChannelUpdateItems({
    channels,
    initialChannels,
    initialNames,
    initialItemSourceByKey,
    savedItemMap,
    runtimeConfig,
    initialRuntimeConfig,
    managesRuntimeConfig,
    providers,
    emptyApiKeyHosts,
    connectionFields,
  });
}

export function channelsAreEqual(left: ChannelConfig, right: ChannelConfig): boolean {
  return (
    left.name === right.name
    && left.displayName === right.displayName
    && left.displayNameValuePresent === right.displayNameValuePresent
    && left.providerId === right.providerId
    && left.providerIdExplicit === right.providerIdExplicit
    && left.protocol === right.protocol
    && left.protocolValuePresent === right.protocolValuePresent
    && left.baseUrl === right.baseUrl
    && left.apiKey === right.apiKey
    && left.credentialField === right.credentialField
    && left.models === right.models
    && left.extraHeaders === right.extraHeaders
    && left.enabled === right.enabled
    && left.enabledValuePresent === right.enabledValuePresent
  );
}

export function buildItemSourceByKey(
  items: Array<{ key: string; value: string; rawValueExists?: boolean }>,
): Map<string, boolean> {
  const sourceByKey = new Map<string, boolean>();
  for (const item of items) {
    sourceByKey.set(item.key.toUpperCase(), item.rawValueExists !== false);
  }
  for (const [key, hasSource] of sourceByKey) {
    if (hasSource) {
      continue;
    }
    const match = CHANNEL_FIELD_KEY_PATTERN.exec(key);
    if (!match) {
      continue;
    }
    const channelName = match[1];
    for (const channelKey of parseChannelFieldKeysFromName(channelName)) {
      if (!sourceByKey.has(channelKey)) {
        sourceByKey.set(channelKey, false);
      }
    }
  }
  return sourceByKey;
}

// Layer the parent-held channel draft on top of the saved items so a remounted
// editor (after switching settings tabs) rehydrates the in-progress draft
// instead of dropping it. Draft entries win and are treated as user-provided.
export function applyChannelDraftItems(
  items: Array<{ key: string; value: string; rawValueExists?: boolean }>,
  draftItems: Array<{ key: string; value: string }> | undefined,
): Array<{ key: string; value: string; rawValueExists?: boolean }> {
  if (!draftItems || draftItems.length === 0) {
    return items;
  }
  const byKey = new Map<string, { key: string; value: string; rawValueExists?: boolean }>();
  for (const item of items) {
    byKey.set(item.key.toUpperCase(), { ...item });
  }
  for (const draftItem of draftItems) {
    const upperKey = draftItem.key.toUpperCase();
    const existing = byKey.get(upperKey);
    byKey.set(upperKey, {
      key: existing?.key ?? draftItem.key,
      value: draftItem.value,
      rawValueExists: true,
    });
  }
  return Array.from(byKey.values());
}
