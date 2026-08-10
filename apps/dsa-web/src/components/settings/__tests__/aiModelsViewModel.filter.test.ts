// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { filterAssignableAvailableModels } from '../aiModelsViewModel';

describe('filterAssignableAvailableModels', () => {
  it('drops models owned by failed connections', () => {
    const models = [
      { route: 'openai/gpt', modelRef: 'ref1', display: 'gpt', connectionName: 'openai' },
      { route: 'deepseek/chat', modelRef: 'ref2', display: 'chat', connectionName: 'deepseek' },
    ] as any;
    const filtered = filterAssignableAvailableModels(models, ['openai']);
    expect(filtered.map((entry) => entry.connectionName)).toEqual(['deepseek']);
  });
});
