// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import type { AvailableModelEntry } from '../../../types/systemConfig';
import { filterAssignableAvailableModels } from '../aiModelsViewModel';

describe('filterAssignableAvailableModels', () => {
  it('drops models owned by failed connections', () => {
    const models: AvailableModelEntry[] = [
      {
        route: 'openai/gpt',
        modelRef: 'ref1',
        display: 'gpt',
        connectionName: 'openai',
      } as AvailableModelEntry,
      {
        route: 'deepseek/chat',
        modelRef: 'ref2',
        display: 'chat',
        connectionName: 'deepseek',
      } as AvailableModelEntry,
    ];
    const filtered = filterAssignableAvailableModels(models, ['openai']);
    expect(filtered.map((entry) => entry.connectionName)).toEqual(['deepseek']);
  });
});
