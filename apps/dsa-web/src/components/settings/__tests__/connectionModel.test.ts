import { describe, expect, it } from 'vitest';
import { deriveConnections } from '../connectionModel';
import type { AvailableModelEntry, LlmProviderCatalogEntry } from '../../../types/systemConfig';

const providers: LlmProviderCatalogEntry[] = [
  { id: 'deepseek', label: 'DeepSeek 官方', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', placeholderModels: '', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
  { id: 'ollama', label: 'Ollama（本地）', protocol: 'ollama', defaultBaseUrl: 'http://127.0.0.1:11434', placeholderModels: '', capabilities: [], requiresApiKey: false, requiresBaseUrl: false, supportsDiscovery: true, isLocal: true, isCustom: false },
];

const availableModels: AvailableModelEntry[] = [
  { route: 'deepseek/deepseek-v4-flash', display: 'deepseek-v4-flash', connection: 'deepseek', provider: 'deepseek' },
  { route: 'ollama/llama3.2', display: 'llama3.2', connection: 'ollama', provider: 'ollama' },
];

describe('deriveConnections', () => {
  it('derives configured/disabled/incomplete status and provider labels', () => {
    const cards = deriveConnections({
      valuesByKey: {
        LLM_CHANNELS: 'deepseek,ollama,proxy',
        LLM_DEEPSEEK_PROTOCOL: 'deepseek',
        LLM_DEEPSEEK_API_KEY: 'sk-ds',
        LLM_DEEPSEEK_MODELS: 'deepseek-v4-flash,deepseek-v4-pro',
        LLM_DEEPSEEK_ENABLED: 'true',
        LLM_OLLAMA_PROTOCOL: 'ollama',
        LLM_OLLAMA_MODELS: 'llama3.2',
        LLM_OLLAMA_ENABLED: 'false',
        LLM_PROXY_PROTOCOL: 'openai',
        LLM_PROXY_MODELS: '',
        LLM_PROXY_ENABLED: 'true',
      },
      providers,
      availableModels,
      taskAssignments: [
        { label: '报告', route: 'deepseek/deepseek-v4-flash' },
        { label: 'Vision', route: 'deepseek/deepseek-v4-flash' },
      ],
    });
    const byName = new Map(cards.map((card) => [card.name, card]));
    // DeepSeek: enabled + key + models -> configured; used by report + Vision.
    expect(byName.get('deepseek')?.status).toBe('configured');
    expect(byName.get('deepseek')?.providerLabel).toBe('DeepSeek 官方');
    expect(byName.get('deepseek')?.modelCount).toBe(2);
    expect(byName.get('deepseek')?.usedByTasks).toEqual(['报告', 'Vision']);
    // Ollama: disabled overrides completeness.
    expect(byName.get('ollama')?.status).toBe('disabled');
    // proxy: enabled but no models and no key -> incomplete.
    expect(byName.get('proxy')?.status).toBe('incomplete');
    expect(byName.get('proxy')?.usedByTasks).toEqual([]);
  });

  it('treats Ollama / local endpoints as key-exempt for completeness', () => {
    const cards = deriveConnections({
      valuesByKey: {
        LLM_CHANNELS: 'ollama',
        LLM_OLLAMA_PROTOCOL: 'ollama',
        LLM_OLLAMA_BASE_URL: 'http://127.0.0.1:11434',
        LLM_OLLAMA_MODELS: 'llama3.2',
        LLM_OLLAMA_ENABLED: 'true',
      },
      providers,
      availableModels,
      taskAssignments: [],
    });
    // No API key, but Ollama is local -> still configured.
    expect(cards[0].status).toBe('configured');
  });
});
