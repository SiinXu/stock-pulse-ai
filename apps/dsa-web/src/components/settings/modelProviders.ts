export interface ModelProvider {
  // Matches the field-group id in categoryFieldGroups (AI_MODEL_GROUPS).
  id: string;
  label: string;
}

// Provider groups that are merged into the single "model providers" sub-category.
export const MODEL_PROVIDERS: ModelProvider[] = [
  { id: 'openai', label: 'OpenAI' },
  { id: 'anthropic', label: 'Anthropic' },
  { id: 'gemini', label: 'Gemini' },
  { id: 'deepseek', label: 'DeepSeek' },
  { id: 'anspire', label: 'Anspire' },
  { id: 'aihubmix', label: 'AIHubmix' },
];

export const MODEL_PROVIDER_GROUP_IDS = new Set<string>(MODEL_PROVIDERS.map((provider) => provider.id));
