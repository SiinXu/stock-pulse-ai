import type {
  LlmConnectionFieldSchema,
  LlmProviderCatalogEntry,
} from '../../types/systemConfig';
import type { UiLanguage } from '../../i18n/uiText';
import {
  hasUnknownConfigContractCondition,
  isFieldEnabledByContract,
  isFieldVisibleByContract,
  resolveFieldRequirement,
} from '../../utils/configConditions';

const MODEL_ROUTE_PROTOCOL_ALIASES: Record<string, string> = {
  vertexai: 'vertex_ai',
  vertex: 'vertex_ai',
  claude: 'anthropic',
  google: 'gemini',
  openai_compatible: 'openai',
  openai_compat: 'openai',
};

// Keep this in sync with normalize_llm_channel_model() on the backend. These
// are LiteLLM route prefixes, not Provider Catalog identities.
const KNOWN_MODEL_ROUTE_PREFIXES = new Set([
  'openai',
  'anthropic',
  'gemini',
  'vertex_ai',
  'deepseek',
  'minimax',
  'ollama',
  'cohere',
  'huggingface',
  'bedrock',
  'sagemaker',
  'azure',
  'replicate',
  'together_ai',
  'palm',
  'text-completion-openai',
  'command-r',
  'groq',
  'cerebras',
  'fireworks_ai',
  'friendliai',
]);

export interface ConnectionRequirementInput {
  provider: LlmProviderCatalogEntry;
  protocol: string;
  baseUrl: string;
  emptyApiKeyHosts?: string[];
}

export interface ConnectionRequirements {
  showApiKey: boolean;
  apiKeyRequired: boolean;
  showProtocol: boolean;
  showBaseUrl: boolean;
  baseUrlRequired: boolean;
  supportsDiscovery: boolean;
}

export interface ConnectionContractValuesInput {
  connectionName: string;
  displayName: string;
  providerId: string;
  provider?: LlmProviderCatalogEntry;
  protocol: string;
  baseUrl: string;
  apiKey: string;
  credentialField?: ConnectionCredentialField;
  models: string | string[];
  extraHeaders?: string;
  enabled: boolean;
  emptyApiKeyHosts?: string[];
  baseUrlVisible?: boolean;
  extraHeadersVisible?: boolean;
}

export type ConnectionCredentialField = 'api_key' | 'api_keys';

export interface ConnectionFieldState {
  visible: boolean;
  enabled: boolean;
  required: boolean;
  unknownCondition: boolean;
  requiresConnectionTest: boolean;
}

const CHINESE_SCRIPT = /[\u3400-\u9fff]/u;

/** Select a Catalog display label without translating Provider identity. */
export function getProviderDisplayLabel(
  provider: LlmProviderCatalogEntry,
  language: UiLanguage,
): string {
  const localized = language === 'en' ? provider.labelEn : provider.labelZh;
  if (localized?.trim()) {
    return localized.trim();
  }
  const legacy = provider.label?.trim();
  if (legacy && (language !== 'en' || !CHINESE_SCRIPT.test(legacy))) {
    return legacy;
  }
  return provider.id;
}

/** Build the value/context map evaluated by the backend-provided contracts. */
export function buildConnectionContractValues({
  connectionName,
  displayName,
  providerId,
  provider,
  protocol,
  baseUrl,
  apiKey,
  credentialField,
  models,
  extraHeaders = '',
  enabled,
  emptyApiKeyHosts = [],
  baseUrlVisible,
  extraHeadersVisible,
}: ConnectionContractValuesInput): Record<string, string> {
  const normalizedBaseUrl = baseUrl.trim().replace(/\/$/, '');
  const normalizedDefaultUrl = (provider?.defaultBaseUrl ?? '').trim().replace(/\/$/, '');
  const parsedModels = Array.isArray(models) ? models : models.split(',');
  const apiKeySegments = apiKey.split(',').map((segment) => segment.trim()).filter(Boolean);
  const resolvedCredentialField = credentialField
    ?? (apiKeySegments.length > 1 ? 'api_keys' : 'api_key');
  const keyRequired = !connectionAllowsEmptyApiKey(protocol, baseUrl, emptyApiKeyHosts);
  const showBaseUrl = baseUrlVisible ?? Boolean(
    provider?.isCustom
    || (normalizedBaseUrl && normalizedBaseUrl !== normalizedDefaultUrl),
  );
  return {
    connection_name: connectionName.trim(),
    display_name: displayName.trim(),
    provider_id: provider?.id ?? providerId.trim(),
    protocol: protocol.trim(),
    base_url: baseUrl.trim(),
    api_key: resolvedCredentialField === 'api_key' ? apiKeySegments.join(',') : '',
    api_keys: resolvedCredentialField === 'api_keys' ? apiKeySegments.join(',') : '',
    models: parsedModels.map((model) => model.trim()).filter(Boolean).join(','),
    extra_headers: extraHeaders.trim(),
    enabled: enabled ? 'true' : 'false',
    api_key_required: keyRequired ? 'true' : 'false',
    api_key_visible: keyRequired || provider?.isCustom || apiKeySegments.length > 0 ? 'true' : 'false',
    base_url_required: provider?.isCustom ? 'true' : 'false',
    base_url_visible: showBaseUrl ? 'true' : 'false',
    extra_headers_visible: (extraHeadersVisible ?? Boolean(extraHeaders.trim())) ? 'true' : 'false',
    protocol_visible: provider?.isCustom
      || Boolean(protocol.trim() && protocol.trim().toLowerCase() !== provider?.protocol.trim().toLowerCase())
      ? 'true'
      : 'false',
  };
}

function normalizeContractValues(values: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [key.toUpperCase(), value]),
  );
}

/** Evaluate the backend field schema with the shared fail-safe AND semantics. */
export function evaluateConnectionFieldStates(
  values: Record<string, string>,
  fields: LlmConnectionFieldSchema[],
): Record<string, ConnectionFieldState> {
  const normalizedValues = normalizeContractValues(values);
  return Object.fromEntries(fields.map((field) => {
    const unknownCondition = hasUnknownConfigContractCondition(field.contract, normalizedValues);
    const visible = isFieldVisibleByContract(field.contract, normalizedValues);
    const requirement = resolveFieldRequirement(field.contract, normalizedValues);
    return [field.key, {
      visible,
      enabled: isFieldEnabledByContract(field.contract, normalizedValues),
      required: visible && requirement === 'required',
      unknownCondition,
      requiresConnectionTest: Boolean(field.contract.requiresConnectionTest),
    }];
  }));
}

/** Return missing visible fields in backend schema order. */
export function validateConnectionContractValues(
  values: Record<string, string>,
  fields: LlmConnectionFieldSchema[],
): string[] {
  const states = evaluateConnectionFieldStates(values, fields);
  return fields
    .filter((field) => states[field.key]?.required && !values[field.key]?.trim())
    .map((field) => field.key);
}

/** Expose unknown operators as a diagnostic instead of silently hiding fields. */
export function hasUnknownConnectionFieldCondition(
  values: Record<string, string>,
  fields: LlmConnectionFieldSchema[],
): boolean {
  return Object.values(evaluateConnectionFieldStates(values, fields))
    .some((state) => state.unknownCondition);
}

/** Return whether the evaluated schema permits model discovery right now. */
export function isConnectionModelDiscoveryEnabled(
  values: Record<string, string>,
  fields: LlmConnectionFieldSchema[],
): boolean {
  const states = evaluateConnectionFieldStates(values, fields);
  const modelsState = states.models;
  if (!modelsState?.visible || !modelsState.enabled || modelsState.unknownCondition) {
    return false;
  }
  if (Object.values(states).some((state) => state.unknownCondition)) {
    return false;
  }
  return fields.every((field) => {
    const state = states[field.key];
    if (field.key === 'models' || !state?.visible || !state.requiresConnectionTest) {
      return true;
    }
    return !state.required || Boolean(values[field.key]?.trim());
  });
}

export function connectionAllowsEmptyApiKey(
  protocol: string,
  baseUrl: string,
  emptyApiKeyHosts: string[] = [],
): boolean {
  if (protocol === 'ollama') {
    return true;
  }
  const endpoint = baseUrl.trim();
  if (!endpoint) {
    return false;
  }
  try {
    return emptyApiKeyHosts.includes(new URL(endpoint).hostname);
  } catch {
    return false;
  }
}

export function resolveConnectionRequirements({
  provider,
  protocol,
  baseUrl,
  emptyApiKeyHosts = [],
}: ConnectionRequirementInput): ConnectionRequirements {
  const allowsEmptyKey = !provider.requiresApiKey
    || connectionAllowsEmptyApiKey(protocol, baseUrl, emptyApiKeyHosts);
  return {
    showApiKey: provider.requiresApiKey,
    apiKeyRequired: provider.requiresApiKey && !allowsEmptyKey,
    showProtocol: provider.isCustom,
    showBaseUrl: provider.isCustom,
    baseUrlRequired: provider.requiresBaseUrl,
    supportsDiscovery: provider.supportsDiscovery,
  };
}

export function suggestConnectionName(existingNames: string[], providerId: string): string {
  const taken = new Set(existingNames.map((name) => name.trim().toLowerCase()));
  const base = providerId.toLowerCase();
  if (!taken.has(base)) {
    return base;
  }
  let counter = 2;
  while (taken.has(`${base}${counter}`)) {
    counter += 1;
  }
  return `${base}${counter}`;
}

export function canonicalModelRoute(protocol: string, model: string): string {
  const trimmed = model.trim();
  if (!trimmed) {
    return '';
  }
  const normalizedProtocol = MODEL_ROUTE_PROTOCOL_ALIASES[protocol.trim().toLowerCase()]
    ?? protocol.trim().toLowerCase();
  const delimiterIndex = trimmed.indexOf('/');
  if (delimiterIndex < 0) {
    return `${normalizedProtocol}/${trimmed}`;
  }

  const rawPrefix = trimmed.slice(0, delimiterIndex);
  const lowerPrefix = rawPrefix.toLowerCase();
  const canonicalPrefix = MODEL_ROUTE_PROTOCOL_ALIASES[lowerPrefix] ?? lowerPrefix;
  const remainder = trimmed.slice(delimiterIndex + 1);
  if (KNOWN_MODEL_ROUTE_PREFIXES.has(lowerPrefix)) {
    return trimmed;
  }
  if (KNOWN_MODEL_ROUTE_PREFIXES.has(canonicalPrefix)) {
    return `${canonicalPrefix}/${remainder}`;
  }
  // A slash may be part of the provider's model id (for example
  // deepseek-ai/DeepSeek-V3), so it is not sufficient evidence that the model
  // already contains a LiteLLM route prefix.
  return `${normalizedProtocol}/${trimmed}`;
}
