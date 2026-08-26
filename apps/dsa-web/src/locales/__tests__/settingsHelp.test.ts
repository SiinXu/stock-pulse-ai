// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { getSettingsHelpContent } from '../settingsHelp';
import { UI_LANGUAGES } from '../../i18n/uiLanguages';

const OVERLAY_FIXTURE_HELP_KEYS = [
  'settings.data_source.RSS_NEWS_FEED_URLS',
  'settings.agent.AGENT_MULTI_STRATEGY_DELIBERATION',
] as const;

describe('fallback model settings help', () => {
  it.each(UI_LANGUAGES)('keeps the overlay fixture help inventory mount-safe for %s', (language) => {
    for (const key of OVERLAY_FIXTURE_HELP_KEYS) {
      const content = getSettingsHelpContent(key, undefined, language);
      expect(content?.title.trim(), `${language}:${key}:title`).not.toBe('');
      expect(content?.summary?.trim(), `${language}:${key}:summary`).not.toBe('');
    }
  });

  it.each(UI_LANGUAGES)('returns complete localized settings help for %s', (language) => {
    const content = getSettingsHelpContent('settings.ai_model.GENERATION_BACKEND', undefined, language);
    expect(content?.title.trim()).not.toBe('');
    expect(content?.summary?.trim()).not.toBe('');
    expect(content?.valueNotes?.length).toBeGreaterThan(0);
  });

  it.each(UI_LANGUAGES)('documents the constrained AlphaSift install sequence for %s', (language) => {
    const content = getSettingsHelpContent(
      'settings.data_source.ALPHASIFT_ENABLED',
      undefined,
      language,
    );
    const usage = content?.usage ?? '';

    expect(usage).toContain('python -m pip install --upgrade --constraint constraints.txt pip');
    expect(usage).toContain(
      'python -m pip install --build-constraint build-constraints.txt -r requirements.txt',
    );
    expect(usage).toContain('python -m pip check');
  });

  it('uses the selected language for unknown-key fallback help', () => {
    const content = getSettingsHelpContent('settings.future.UNKNOWN', 'Backend-provided summary', 'ja');

    expect(content?.title.trim()).not.toBe('');
    expect(content?.title).not.toBe('配置说明');
    expect(content?.summary).toBe('Backend-provided summary');
  });

  it('uses field-specific descriptions for shared market-regime help', () => {
    const description = 'Field-specific market-regime guidance';
    const content = getSettingsHelpContent(
      'settings.agent.market_regime',
      description,
      'en-US',
    );

    expect(content?.summary).toBe(description);
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
    ['en-US', 'end-of-run reflection', 'post-mortem'],
    ['zh-CN', '运行结束反思', '后验'],
  ])('documents that AGENT_MODE_BUDGET_MAX_LLM_TURNS includes reflection in %s', (
    locale,
    reflectionText,
    postmortemText,
  ) => {
    const content = getSettingsHelpContent(
      'settings.agent.AGENT_MODE_BUDGET_MAX_LLM_TURNS',
      undefined,
      locale,
    );
    const copy = JSON.stringify(content);
    expect(copy).toContain(reflectionText);
    expect(copy).toContain(postmortemText);
    expect(copy).toContain('budget_skipped');
  });

  it.each(UI_LANGUAGES)('keeps full catalog-description skill retrieval help for %s', (language) => {
    const content = getSettingsHelpContent('settings.agent.AGENT_SKILL_RETRIEVAL_K', undefined, language);
    const fieldContent = getSettingsHelpContent('AGENT_SKILL_RETRIEVAL_K', undefined, language);
    expect(content?.title.trim(), `${language}:title`).not.toBe('');
    expect(content?.summary?.trim(), `${language}:summary`).not.toBe('');
    expect(content?.usage?.trim(), `${language}:usage`).not.toBe('');
    expect(content?.impact?.length, `${language}:impact`).toBeGreaterThan(0);
    expect(content?.notes?.length, `${language}:notes`).toBeGreaterThanOrEqual(2);
    expect(content?.valueNotes?.length, `${language}:valueNotes`).toBeGreaterThan(0);
    expect(content?.examples).toEqual(['AGENT_SKILL_RETRIEVAL_K=0', 'AGENT_SKILL_RETRIEVAL_K=2']);
    expect(fieldContent?.title).toBe(content?.title);
    expect(fieldContent?.summary).toBe(content?.summary);
    const copy = JSON.stringify(content);
    expect(copy).toContain('AGENT_SKILL_RETRIEVAL_K');
    expect(copy).toContain('AGENT_SKILLS');
    expect(copy).toMatch(/manual/);
    expect(copy).toMatch(/\ball\b/);
    if (language !== 'en' && language !== 'zh') {
      expect(content?.title).not.toBe(
        getSettingsHelpContent('settings.agent.AGENT_SKILL_RETRIEVAL_K', undefined, 'en')?.title,
      );
    }
  });

  it.each(UI_LANGUAGES)('keeps full adversarial red-team help for %s', (language) => {
    const content = getSettingsHelpContent('settings.agent.AGENT_RED_TEAM_ENABLED', undefined, language);
    const fieldContent = getSettingsHelpContent('AGENT_RED_TEAM_ENABLED', undefined, language);
    expect(content?.title.trim(), `${language}:title`).not.toBe('');
    expect(content?.summary?.trim(), `${language}:summary`).not.toBe('');
    expect(content?.usage?.trim(), `${language}:usage`).not.toBe('');
    expect(content?.impact?.length, `${language}:impact`).toBeGreaterThan(0);
    expect(content?.notes?.length, `${language}:notes`).toBeGreaterThan(0);
    expect(content?.valueNotes?.length, `${language}:valueNotes`).toBeGreaterThan(0);
    expect(content?.examples).toEqual(['AGENT_RED_TEAM_ENABLED=false', 'AGENT_RED_TEAM_ENABLED=true']);
    expect(fieldContent?.title).toBe(content?.title);
    expect(fieldContent?.summary).toBe(content?.summary);
    const copy = JSON.stringify(content);
    expect(copy).toContain('decision_type');
    expect(copy).toMatch(/Chat/i);
    if (language !== 'en' && language !== 'zh') {
      expect(content?.title).not.toBe(
        getSettingsHelpContent('settings.agent.AGENT_RED_TEAM_ENABLED', undefined, 'en')?.title,
      );
    }
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
