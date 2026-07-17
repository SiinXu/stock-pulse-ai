import { describe, expect, it } from 'vitest';
import type {
  AnalysisPhase,
  MarketPhaseSummary,
  MarketPhaseValue,
} from '../../types/analysis';
import type { UiLanguage } from '../../i18n/uiText';
import {
  getMarketPhaseSummaryLabel,
  getPartialBarLabel,
  getRequestedPhaseLabel,
  stripMarketPhaseSummaryPrefix,
} from '../marketPhase';

const ADDITIONAL_LANGUAGES = [
  'zh-TW',
  'ja',
  'ko',
  'de',
  'es',
  'ms',
  'fr',
  'id',
] as const satisfies readonly UiLanguage[];

const REQUEST_PHASES = [
  'auto',
  'premarket',
  'intraday',
  'postmarket',
] as const satisfies readonly AnalysisPhase[];

const MARKET_PHASES = [
  'premarket',
  'intraday',
  'lunch_break',
  'closing_auction',
  'postmarket',
  'non_trading',
  'unknown',
] as const satisfies readonly MarketPhaseValue[];

const createSummary = (
  phase: MarketPhaseValue,
  market: string | null = 'us',
): MarketPhaseSummary => ({
  phase,
  market,
  warnings: [],
});

describe('market phase labels', () => {
  it('formats representative requested and resolved phases', () => {
    expect(getRequestedPhaseLabel('intraday', 'en')).toBe('Requested phase: Intraday');
    expect(getRequestedPhaseLabel('postmarket', 'zh')).toBe('请求阶段: 盘后');
    expect(getMarketPhaseSummaryLabel(createSummary('lunch_break', ' hk '), 'en'))
      .toBe('Market phase: HK · Lunch break');
    expect(getMarketPhaseSummaryLabel(createSummary('unknown', null), 'zh'))
      .toBe('市场阶段: 阶段未知');
  });

  it.each(ADDITIONAL_LANGUAGES)('provides complete market phase copy for %s', (language) => {
    for (const phase of REQUEST_PHASES) {
      const localized = getRequestedPhaseLabel(phase, language);
      expect(localized).toMatch(/^.+: .+$/u);
      expect(localized).not.toBe(getRequestedPhaseLabel(phase, 'en'));
      expect(localized).not.toBe(getRequestedPhaseLabel(phase, 'zh'));
    }

    for (const phase of MARKET_PHASES) {
      const localized = getMarketPhaseSummaryLabel(createSummary(phase), language);
      expect(localized).toContain(': US · ');
      expect(localized).not.toBe(getMarketPhaseSummaryLabel(createSummary(phase), 'en'));
      expect(localized).not.toBe(getMarketPhaseSummaryLabel(createSummary(phase), 'zh'));
    }

    expect(getPartialBarLabel(language)).not.toBe(getPartialBarLabel('en'));
    expect(getPartialBarLabel(language)).not.toBe(getPartialBarLabel('zh'));
  });

  it('uses Traditional Chinese rather than Simplified Chinese or English copy', () => {
    const requested = getRequestedPhaseLabel('premarket', 'zh-TW');
    const summary = getMarketPhaseSummaryLabel(createSummary('lunch_break', 'hk'), 'zh-TW');
    const partialBar = getPartialBarLabel('zh-TW');
    const combined = [requested, summary, partialBar].join(' ');

    expect(requested).toContain('請求階段');
    expect(requested).toContain('盤前');
    expect(summary).toContain('市場階段');
    expect(summary).toContain('HK · 午間休市');
    expect(partialBar).toBe('日線未完成');
    expect(combined).not.toMatch(/[请阶场盘间线]/u);
    expect(combined).not.toMatch(/Requested phase|Pre-market|Market phase|Lunch break|Partial bar/u);
  });

  it('handles missing values and strips both colon styles', () => {
    expect(getRequestedPhaseLabel(null, 'ja')).toBeNull();
    expect(getMarketPhaseSummaryLabel(null, 'de')).toBeNull();
    expect(getRequestedPhaseLabel('auto', null)).toBe('请求阶段: 自动阶段');
    expect(stripMarketPhaseSummaryPrefix('Market phase: US · Intraday'))
      .toBe('US · Intraday');
    expect(stripMarketPhaseSummaryPrefix('市場階段：HK · 盤中'))
      .toBe('HK · 盤中');
    expect(stripMarketPhaseSummaryPrefix(null)).toBeNull();
  });
});
