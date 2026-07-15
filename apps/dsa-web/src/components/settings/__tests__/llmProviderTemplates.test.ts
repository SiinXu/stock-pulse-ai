import { describe, expect, it } from 'vitest';
import {
  LLM_PROVIDER_CAPABILITY_LABELS,
  getCapabilityLabel,
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

  it('does not ship concrete model IDs (models come from discovery / manual entry)', () => {
    const source = JSON.stringify({ LLM_PROVIDER_CAPABILITY_LABELS });
    expect(source).not.toMatch(/gpt-\d|claude-(sonnet|opus|haiku)|gemini-\d|deepseek-v\d|qwen\d|llama\d/i);
  });
});
