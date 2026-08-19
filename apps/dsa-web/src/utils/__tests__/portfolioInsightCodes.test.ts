// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeAll, describe, expect, it } from 'vitest';
import { loadAllUiLanguageTranslations } from '../../i18n/translations';
import { UI_LANGUAGES } from '../../i18n/uiLanguages';
import {
  getPortfolioInsightCodes,
  loadPortfolioInsightCodes,
  SOURCE_PORTFOLIO_INSIGHT_CODES,
} from '../../locales/portfolioInsightCodes';
import {
  formatPortfolioBasketDirection,
  formatPortfolioBasketReason,
  formatPortfolioHealthBand,
  formatPortfolioHealthInsight,
  formatPortfolioInsightStatus,
  formatPortfolioRebalanceAction,
  formatPortfolioRebalanceRationale,
  formatPortfolioSharedRisk,
  formatPortfolioStressExcludedReason,
  formatPortfolioStressScenario,
} from '../dataQualityFormat/portfolioInsights';
import { formatUnknownMachineCode } from '../dataQualityFormat/unknownCode';

describe('portfolio insight presentation', () => {
  beforeAll(async () => {
    await loadAllUiLanguageTranslations();
    await Promise.all(UI_LANGUAGES.map((language) => loadPortfolioInsightCodes(language).catch(() => undefined)));
  });

  it('localizes known health bands, insights, and statuses', () => {
    expect(formatPortfolioHealthBand('healthy', 'zh')).toBe('健康');
    expect(formatPortfolioHealthBand('caution', 'en')).toBe('Caution');
    expect(formatPortfolioHealthInsight({
      code: 'concentration_top_name',
      symbol: 'AAPL',
      value: 42.5,
      threshold: 25,
    }, 'en')).toContain('AAPL');
    expect(formatPortfolioHealthInsight({
      code: 'concentration_top_name',
      symbol: 'AAPL',
      value: 42.5,
      threshold: 25,
    }, 'en')).not.toContain('consider reducing');
    expect(formatPortfolioInsightStatus('insufficient_data', 'en')).toBe('Insufficient data');
    expect(formatPortfolioInsightStatus('refused', 'zh')).toBe('已拒绝');
    expect(formatPortfolioInsightStatus('ok', 'en')).toBe('OK');
  });

  it('localizes rebalance actions from structured fields instead of English rationale', () => {
    expect(formatPortfolioRebalanceAction('trim', 'zh')).toBe('减仓');
    expect(formatPortfolioRebalanceRationale({
      action: 'trim',
      symbol: 'AAPL',
      fromWeightPct: 20,
      toWeightPct: 12,
    }, 'en')).toBe('Trim AAPL from 20.0% toward 12.0%.');
    expect(formatPortfolioRebalanceRationale({
      action: 'hold',
      symbol: 'MSFT',
      currentWeightPct: 8,
      targetWeightPctLow: 5,
      targetWeightPctHigh: 12,
    }, 'en')).toContain('target band');
  });

  it('localizes basket reasons, directions, and shared-risk kinds', () => {
    expect(formatPortfolioBasketReason('price_unavailable', 'en')).toBe('No usable stored daily close.');
    expect(formatPortfolioStressExcludedReason('price_unavailable', 'zh')).toBe('没有可用的已存储收盘价。');
    expect(formatPortfolioStressExcludedReason('non_positive_market_value', 'en')).toBe(
      'Market value is not positive, so the position is excluded from the stress run.',
    );
    expect(formatPortfolioBasketDirection('positive', 'zh')).toBe('正相关');
    expect(formatPortfolioSharedRisk({
      kind: 'high_correlation_cluster',
      size: 3,
    }, 'en').kindLabel).toBe('High-correlation cluster');
    expect(formatPortfolioSharedRisk({
      kind: 'sector_concentration',
      size: 2,
      sector: 'Technology',
    }, 'en').summary).toContain('Technology');
  });

  it('localizes built-in stress scenarios by id', () => {
    expect(formatPortfolioStressScenario({
      id: 'market_down_10',
      name: 'Broad market -10%',
      description: 'Instantaneous equity market factor shock of -10%.',
    }, 'zh').name).toBe('大盘下跌 10%');
    expect(formatPortfolioStressScenario({
      id: 'custom_yaml_shock',
      name: 'A custom English name',
      description: 'Free-form English description',
    }, 'en').name).toBe(formatUnknownMachineCode('custom_yaml_shock', 'en'));
    expect(formatPortfolioStressScenario({
      id: 'custom_yaml_shock',
      name: 'A custom English name',
      description: 'Free-form English description',
    }, 'en').description).toContain('Diagnostic:');
  });

  it('keeps unknown codes visible as sanitized diagnostics', () => {
    expect(formatPortfolioHealthBand('mystery_band', 'en')).toBe(
      formatUnknownMachineCode('mystery_band', 'en'),
    );
    expect(formatPortfolioHealthInsight({ code: 'not_a_real_insight' }, 'zh')).toBe(
      formatUnknownMachineCode('not_a_real_insight', 'zh'),
    );
    expect(formatPortfolioHealthInsight({
      code: 'Position AAPL weight 40% exceeds concentration threshold',
    }, 'en')).toBe(formatUnknownMachineCode('unknown', 'en'));
    expect(formatPortfolioRebalanceAction('zoom', 'ja')).toBe(
      formatUnknownMachineCode('zoom', 'ja'),
    );
    expect(formatPortfolioBasketReason('quote_timeout', 'ko')).toBe(
      formatUnknownMachineCode('quote_timeout', 'ko'),
    );
    expect(formatPortfolioStressExcludedReason('quote_timeout', 'ko')).toBe(
      formatUnknownMachineCode('quote_timeout', 'ko'),
    );
  });

  it('has the same insight-code keys in every UI language', () => {
    const expected = Object.keys(SOURCE_PORTFOLIO_INSIGHT_CODES.en);
    for (const language of UI_LANGUAGES) {
      expect(Object.keys(getPortfolioInsightCodes(language))).toEqual(expected);
    }
  });
});
