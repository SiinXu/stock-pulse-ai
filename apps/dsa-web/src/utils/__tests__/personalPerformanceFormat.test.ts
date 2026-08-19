// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeAll, describe, expect, it } from 'vitest';
import { loadAllUiLanguageTranslations } from '../../i18n/translations';
import { UI_LANGUAGES } from '../../i18n/uiLanguages';
import {
  getPersonalPerformanceReasonLabels,
  loadPersonalPerformanceReasonLabels,
  PERSONAL_PERFORMANCE_REASON_LABELS,
} from '../../locales/personalPerformanceReasons';
import {
  formatPaperDecisionReason,
  formatPaperDecisionSide,
} from '../dataQualityFormat/personalPerformance';
import { formatUnknownMachineCode } from '../dataQualityFormat/unknownCode';

describe('personal performance presentation', () => {
  beforeAll(async () => {
    await loadAllUiLanguageTranslations();
    await Promise.all(UI_LANGUAGES.map((language) => loadPersonalPerformanceReasonLabels(language)));
  });

  it('localizes known trade sides through PORTFOLIO_SIDE_LABELS', () => {
    expect(formatPaperDecisionSide('buy', 'zh')).toBe('买入');
    expect(formatPaperDecisionSide('SELL', 'en')).toBe('Sell');
    expect(formatPaperDecisionSide('buy', 'ja')).toBe('買い');
    expect(formatPaperDecisionSide('', 'en')).toBe('—');
    expect(formatPaperDecisionSide(null, 'zh')).toBe('—');
  });

  it('localizes known reason codes instead of server English prose', () => {
    expect(formatPaperDecisionReason({
      code: 'no_analysis_support',
      message: 'No DecisionSignal or analysis plan was linked to this trade.',
    }, 'zh')).toBe('这笔成交没有关联的 DecisionSignal 或分析计划。');
    expect(formatPaperDecisionReason({
      code: 'action_aligned',
      message: "Signal action 'buy' aligns with trade side 'buy'.",
    }, 'en')).toBe('Signal action aligns with the trade side.');
    expect(formatPaperDecisionReason({
      code: 'action_aligned',
      message: "Signal action 'buy' aligns with trade side 'buy'.",
    }, 'en')).not.toContain("'buy'");
  });

  it('keeps unknown or prose-shaped codes as sanitized diagnostics', () => {
    expect(formatPaperDecisionReason({ code: 'brand_new_reason' }, 'en')).toBe(
      formatUnknownMachineCode('brand_new_reason', 'en'),
    );
    expect(formatPaperDecisionReason({
      code: 'No DecisionSignal or analysis plan was linked to this trade.',
      message: 'No DecisionSignal or analysis plan was linked to this trade.',
    }, 'en')).toBe(formatUnknownMachineCode(
      'No DecisionSignal or analysis plan was linked to this trade.',
      'en',
    ));
    expect(formatPaperDecisionReason({
      code: 'No DecisionSignal or analysis plan was linked to this trade.',
    }, 'en')).not.toMatch(/^No DecisionSignal or analysis plan was linked to this trade\.$/);
    expect(formatPaperDecisionReason({ code: '<script>alert(1)</script>' }, 'zh')).toBe(
      formatUnknownMachineCode('<script>alert(1)</script>', 'zh'),
    );
    expect(formatPaperDecisionReason({ code: '<script>alert(1)</script>' }, 'zh')).not.toContain('<script>');
  });

  it('has the same reason keys in every UI language', () => {
    const expected = Object.keys(PERSONAL_PERFORMANCE_REASON_LABELS.en);
    for (const language of UI_LANGUAGES) {
      const catalog = getPersonalPerformanceReasonLabels(language);
      expect(Object.keys(catalog)).toEqual(expected);
      for (const key of expected) {
        expect(catalog[key as keyof typeof catalog]).not.toBe('');
      }
    }
  });
});
