import { describe, expect, it } from 'vitest';
import { getStrategyDisplay } from '../strategyDisplay';

describe('getStrategyDisplay', () => {
  it('localizes known built-in strategies by stable id', () => {
    expect(getStrategyDisplay({ id: 'dual_low', name: '双低' }, 'en').name).toBe('Dual-low selection');
    expect(getStrategyDisplay({ id: 'bull_trend', name: '默认多头趋势' }, 'en').name).toBe('Default bull trend');
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
});
