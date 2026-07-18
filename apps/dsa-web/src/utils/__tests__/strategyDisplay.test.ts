// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { getStrategyDisplay } from '../strategyDisplay';

describe('getStrategyDisplay', () => {
  it('localizes known built-in strategies by stable id', () => {
    expect(getStrategyDisplay({ id: 'dual_low', name: '双低' }, 'en').name).toBe('Dual-low selection');
    expect(getStrategyDisplay({ id: 'bull_trend', name: '默认多头趋势' }, 'en').name).toBe('Default bull trend');
  });

  it('preserves server-provided Simplified Chinese and uses the built-in Traditional Chinese copy', () => {
    expect(getStrategyDisplay({ id: 'bull_trend', name: '趋势分析' }, 'zh').name).toBe('趋势分析');
    expect(getStrategyDisplay({ id: 'bull_trend', name: '趋势分析' }, 'zh-TW').name).toBe('預設多頭趨勢');
  });

  it('prefers explicit API locale fields when supplied', () => {
    expect(getStrategyDisplay({ id: 'dual_low', nameEn: 'API English name' }, 'en').name).toBe('API English name');
  });

  it('preserves server copy for unknown third-party strategies', () => {
    expect(getStrategyDisplay({ id: 'custom_alpha', name: 'Vendor Alpha', description: 'Vendor copy' }, 'en')).toEqual({
      name: 'Vendor Alpha',
      description: 'Vendor copy',
      category: 'custom_alpha',
    });
  });

  it('prefers Chinese API fields for Traditional Chinese third-party strategies', () => {
    expect(getStrategyDisplay({
      id: 'custom_alpha',
      nameZh: '自定义策略',
      nameEn: 'Custom strategy',
      descriptionZh: '中文说明',
      descriptionEn: 'English description',
      categoryZh: '自定义',
      categoryEn: 'Custom',
    }, 'zh-TW')).toEqual({
      name: '自定义策略',
      description: '中文说明',
      category: '自定义',
    });
  });
});
