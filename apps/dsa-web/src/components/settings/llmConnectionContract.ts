import type { LlmProviderCatalogEntry } from '../../types/systemConfig';

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
