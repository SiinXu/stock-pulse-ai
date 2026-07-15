import { describe, expect, it } from 'vitest';
import { getStrategyDisplay } from '../strategyDisplay';

describe('getStrategyDisplay', () => {
  it('localizes built-in strategies by stable ID instead of their server name', () => {
    const source = {
      id: 'bull_trend',
      name: '默认多头趋势',
      description: '服务端中文描述',
      category: 'trend',
    };

    expect(getStrategyDisplay(source, 'en')).toEqual({
      name: 'Bull Trend',
      description: 'Identifies bullish alignment, trend continuation, and pullback entries.',
      category: 'Trend',
    });
    expect(getStrategyDisplay(source, 'zh').name).toBe('默认多头趋势');
  });

  it('prefers language-specific API fields when they are present', () => {
    const source = {
      id: 'partner_strategy',
      name: 'Partner default',
      nameZh: '合作方策略',
      nameEn: 'Partner Strategy',
      description_zh: '合作方中文描述',
      description_en: 'Partner description',
      categoryZh: '合作方分类',
      categoryEn: 'Partner category',
    };

    expect(getStrategyDisplay(source, 'zh')).toEqual({
      name: '合作方策略',
      description: '合作方中文描述',
      category: '合作方分类',
    });
    expect(getStrategyDisplay(source, 'en')).toEqual({
      name: 'Partner Strategy',
      description: 'Partner description',
      category: 'Partner category',
    });
  });

  it('preserves unknown third-party values without name-based translation', () => {
    const source = {
      id: 'third_party_custom',
      name: '第三方原始名称',
      description: '原始描述',
      category: '原始分类',
    };

    expect(getStrategyDisplay(source, 'en')).toEqual({
      name: '第三方原始名称',
      description: '原始描述',
      category: '原始分类',
    });
  });
});
