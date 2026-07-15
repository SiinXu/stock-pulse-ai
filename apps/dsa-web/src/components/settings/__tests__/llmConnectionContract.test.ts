import { describe, expect, it } from 'vitest';
import { canonicalModelRoute } from '../llmConnectionContract';

describe('canonicalModelRoute', () => {
  it('adds the connection protocol to bare model ids', () => {
    expect(canonicalModelRoute('openai', 'gpt-4o-mini')).toBe('openai/gpt-4o-mini');
  });

  it('keeps recognized LiteLLM route prefixes', () => {
    expect(canonicalModelRoute('openai', 'anthropic/claude-sonnet-4')).toBe('anthropic/claude-sonnet-4');
  });

  it('prefixes slash-containing provider model ids exactly like the backend', () => {
    expect(canonicalModelRoute('openai', 'deepseek-ai/DeepSeek-V3')).toBe(
      'openai/deepseek-ai/DeepSeek-V3',
    );
  });

  it('canonicalizes supported route aliases', () => {
    expect(canonicalModelRoute('openai', 'google/gemini-2.5-pro')).toBe('gemini/gemini-2.5-pro');
  });
});
