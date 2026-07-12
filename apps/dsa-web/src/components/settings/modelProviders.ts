export interface ModelProvider {
  // Matches the field-group id in categoryFieldGroups (AI_MODEL_GROUPS).
  id: string;
  label: string;
  // Keys that decide the configured badge (credentials / enable toggle only, so
  // default model names or base URLs don't make a provider look configured).
  configuredKeys: string[];
}

// Provider groups that are merged into the single "model providers" sub-category.
// Anspire's credential (ANSPIRE_API_KEYS) lives under data providers, so its LLM
// gateway counts as configured only when explicitly enabled here.
export const MODEL_PROVIDERS: ModelProvider[] = [
  { id: 'openai', label: 'OpenAI', configuredKeys: ['OPENAI_API_KEY', 'OPENAI_API_KEYS'] },
  { id: 'anthropic', label: 'Anthropic', configuredKeys: ['ANTHROPIC_API_KEY', 'ANTHROPIC_API_KEYS'] },
  { id: 'gemini', label: 'Gemini', configuredKeys: ['GEMINI_API_KEY', 'GEMINI_API_KEYS'] },
  { id: 'deepseek', label: 'DeepSeek', configuredKeys: ['DEEPSEEK_API_KEY', 'DEEPSEEK_API_KEYS'] },
  { id: 'anspire', label: 'Anspire', configuredKeys: ['ANSPIRE_LLM_ENABLED'] },
  { id: 'aihubmix', label: 'AIHubmix', configuredKeys: ['AIHUBMIX_KEY'] },
];

export const MODEL_PROVIDER_GROUP_IDS = new Set<string>(MODEL_PROVIDERS.map((provider) => provider.id));
