// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { getCategoryFieldGroupId, getCategoryFieldGroupOrder } from '../categoryFieldGroups';

describe('categoryFieldGroups', () => {
  it('does not encode provider identities in AI model field groups', () => {
    const groupIds = getCategoryFieldGroupOrder('ai_model')?.map((group) => group.id) ?? [];

    expect(groupIds).not.toEqual(expect.arrayContaining([
      'openai',
      'anthropic',
      'gemini',
      'deepseek',
      'anspire',
      'aihubmix',
    ]));
  });

  it('keeps provider resilience and cache controls out of the generic other group', () => {
    for (const key of [
      'PROVIDER_CIRCUIT_BREAKER_ENABLED',
      'PROVIDER_ADAPTIVE_PRIORITY_ENABLED',
      'PROVIDER_DAILY_CACHE_ENABLED',
      'PROVIDER_DAILY_CACHE_PERSISTENT_MAX_ENTRIES',
    ]) {
      expect(getCategoryFieldGroupId('data_source', key), key).toBe('providerReliability');
    }
  });
});
