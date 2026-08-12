// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { getSettingsHelpContent } from '../settingsHelp';
import {
  EDUCATION_HELP_KEYS,
  beginnerRiskHelpKey,
  riskGateStatusHelpKey,
  riskScoreLevelHelpKey,
} from '../educationHelpKeys';

const ALL_KEYS = Object.values(EDUCATION_HELP_KEYS);

describe('education help inventory (Issue #201)', () => {
  it.each(['zh', 'en'] as const)('provides what/why/means content for every education key in %s', (language) => {
    for (const key of ALL_KEYS) {
      const content = getSettingsHelpContent(key, undefined, language);
      expect(content?.title.trim(), `${language}:${key}:title`).not.toBe('');
      expect(content?.summary?.trim(), `${language}:${key}:summary`).not.toBe('');
      expect(content?.usage?.trim(), `${language}:${key}:usage`).not.toBe('');
      expect(content?.impact?.[0]?.trim(), `${language}:${key}:impact`).not.toBe('');
    }
  });

  it('maps risk gate statuses to stable help keys', () => {
    expect(riskGateStatusHelpKey('pass')).toBe(EDUCATION_HELP_KEYS.riskGatePass);
    expect(riskGateStatusHelpKey('reject')).toBe(EDUCATION_HELP_KEYS.riskGateReject);
    expect(riskGateStatusHelpKey('not_evaluated')).toBe(EDUCATION_HELP_KEYS.riskGateNotEvaluated);
  });

  it('maps beginner and heatmap risk bands', () => {
    expect(beginnerRiskHelpKey('elevated')).toBe(EDUCATION_HELP_KEYS.beginnerRiskElevated);
    expect(riskScoreLevelHelpKey('low')).toBe(EDUCATION_HELP_KEYS.riskLevelLow);
    expect(riskScoreLevelHelpKey('missing')).toBeNull();
  });
});
