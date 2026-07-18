// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { getCategoryFieldGroupOrder } from '../categoryFieldGroups';

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
});
