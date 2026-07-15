import { describe, expect, it } from 'vitest';
import {
  LLM_PROVIDER_CAPABILITY_LABELS,
  PROVIDER_PRESENTATION_BY_ID,
  getCapabilityLabel,
  getProviderPresentation,
} from '../llmProviderTemplates';

describe('llmProviderTemplates (presentation-only)', () => {
  it('only defines static capability labels for the provider UI hints', () => {
    expect(Object.keys(LLM_PROVIDER_CAPABILITY_LABELS).sort()).toEqual([
      'aggregator',
      'local-runtime',
      'model-discovery',
      'official-api',
      'openai-compatible',
      'vision',
    ]);
    expect(LLM_PROVIDER_CAPABILITY_LABELS).not.toHaveProperty('json');
    expect(LLM_PROVIDER_CAPABILITY_LABELS).not.toHaveProperty('tools');
  });

  it('resolves capability labels safely, returning undefined for unknown ids', () => {
    expect(getCapabilityLabel('openai-compatible')?.label).toBe('OpenAI 兼容');
    expect(getCapabilityLabel('json')).toBeUndefined();
    expect(getCapabilityLabel('constructor')).toBeUndefined();
  });

  it('keeps focused config hints on providers with common setup pitfalls', () => {
    expect(PROVIDER_PRESENTATION_BY_ID.ollama.configHint).toContain('Ollama 服务');
    expect(PROVIDER_PRESENTATION_BY_ID.siliconflow.configHint).toContain('API 密钥');
    expect(PROVIDER_PRESENTATION_BY_ID.openrouter.configHint).toContain('API 密钥');
    expect(PROVIDER_PRESENTATION_BY_ID.volcengine.configHint).toContain('endpoint');
    expect(getProviderPresentation('openai').configHint).toBeUndefined();
  });

  it('does not duplicate provider URLs or business metadata', () => {
    expect(JSON.stringify(PROVIDER_PRESENTATION_BY_ID)).not.toMatch(/https?:\/\//);
  });

  it('returns an empty presentation for unknown / custom provider ids', () => {
    expect(getProviderPresentation('custom')).toEqual({});
    expect(getProviderPresentation('minimax2')).toEqual({});
    expect(getProviderPresentation('constructor')).toEqual({});
    expect(getProviderPresentation('openrouter').configHint).toContain('API 密钥');
  });

  it('does not ship concrete model IDs (models come from discovery / manual entry)', () => {
    const source = JSON.stringify({ LLM_PROVIDER_CAPABILITY_LABELS, PROVIDER_PRESENTATION_BY_ID });
    expect(source).not.toMatch(/gpt-\d|claude-(sonnet|opus|haiku)|gemini-\d|deepseek-v\d|qwen\d|llama\d/i);
  });
});
