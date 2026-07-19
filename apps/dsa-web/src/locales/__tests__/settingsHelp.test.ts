// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { getSettingsHelpContent } from '../settingsHelp';
import { UI_LANGUAGES } from '../../i18n/uiLanguages';

describe('fallback model settings help', () => {
  it.each(UI_LANGUAGES)('returns complete localized settings help for %s', (language) => {
    const content = getSettingsHelpContent('settings.ai_model.GENERATION_BACKEND', undefined, language);
    expect(content?.title.trim()).not.toBe('');
    expect(content?.summary?.trim()).not.toBe('');
    expect(content?.valueNotes?.length).toBeGreaterThan(0);
  });

  it('uses the selected language for unknown-key fallback help', () => {
    const content = getSettingsHelpContent('settings.future.UNKNOWN', 'Backend-provided summary', 'ja');

    expect(content?.title.trim()).not.toBe('');
    expect(content?.title).not.toBe('配置说明');
    expect(content?.summary).toBe('Backend-provided summary');
  });

  it.each(['zh-CN', 'en-US'])('uses StockPulse branding in user-facing settings help for %s', (locale) => {
    const generationHelp = getSettingsHelpContent('settings.ai_model.GENERATION_BACKEND', undefined, locale);
    const alphaSiftHelp = getSettingsHelpContent('settings.data_source.ALPHASIFT_ENABLED', undefined, locale);
    const copy = JSON.stringify([generationHelp, alphaSiftHelp]);

    expect(copy).toContain('StockPulse');
    expect(copy).not.toMatch(/\bDSA\b/);
    expect(copy).toContain('alphasift.dsa_adapter');
  });

  it.each([
    ['zh-CN', '保存不会静默清理', '显式替换或删除'],
    ['en-US', 'saving never removes them silently', 'Replace or remove unavailable values explicitly'],
  ])('documents stale-value preservation in %s', (locale, preservationText, actionText) => {
    const content = getSettingsHelpContent(
      'settings.ai_model.LITELLM_FALLBACK_MODELS',
      undefined,
      locale,
    );

    expect(content?.valueNotes?.join(' ')).toContain(preservationText);
    expect(content?.notes?.join(' ')).toContain(actionText);
  });

  it.each([
    ['zh-CN', '失效引用会保留并标记不可用', '显式替换或删除'],
    ['en-US', 'stale references remain marked unavailable', 'explicitly replaces or removes'],
  ])('keeps generic Connection model help consistent in %s', (locale, preservationText, actionText) => {
    const content = getSettingsHelpContent(
      'settings.llm_channel.models',
      undefined,
      locale,
    );

    expect(content?.impact?.join(' ')).toContain(preservationText);
    expect(content?.impact?.join(' ')).toContain(actionText);
  });
});
