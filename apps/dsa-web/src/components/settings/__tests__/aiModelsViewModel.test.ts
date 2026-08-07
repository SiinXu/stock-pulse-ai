// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import type { AvailableModelEntry } from '../../../types/systemConfig';
import { buildModelSelectorOptions } from '../aiModelsViewModel';

describe('buildModelSelectorOptions', () => {
  it('falls back to the route and does not repeat identical provider and connection labels', () => {
    const model: AvailableModelEntry = {
      modelRef: 'modelref:v1:custom:minimax%2Fminimax-m3',
      route: 'minimax/minimax-m3',
      display: '',
      connection: 'custom',
      connectionId: 'custom',
      connectionName: '自定义兼容服务',
      provider: 'openai',
      providerId: 'custom',
      providerLabel: '自定义兼容服务',
      available: true,
    };

    expect(buildModelSelectorOptions([model], [], 'zh')).toEqual([
      expect.objectContaining({
        label: 'minimax/minimax-m3',
        sublabel: '自定义兼容服务',
      }),
    ]);
  });
});
