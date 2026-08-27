// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Settings-help `examples` are configuration literals, not inventory keys.
 */
import { beforeAll, describe, expect, it } from 'vitest';
import {
  getLoadedUiLanguageTranslations,
  loadAllUiLanguageTranslations,
  SOURCE_UI_TRANSLATIONS,
  UI_TRANSLATION_KEYS,
} from '../translations';
import { ADDITIONAL_UI_LANGUAGES } from '../uiLanguages';
import { assertSettingsHelpExamplesParity } from '../createUiLanguageRecord';
import { getSettingsHelpContent } from '../../locales/settingsHelp';
import settingsHelpEnUS from '../../locales/settingsHelp.en';
import settingsHelpZhCN from '../../locales/settingsHelp.zh';

const EXAMPLES_KEY_PATTERN = /^locales\.settingsHelp\.SETTINGS_HELP_MAPS\..+\.examples\.\d+$/;

describe('settings-help examples literal contract', () => {
  beforeAll(async () => {
    await loadAllUiLanguageTranslations();
  });

  it('keeps per-symbol episode-forget help out of extra-locale inventories', () => {
    const marker = 'Per-symbol episode row cap after that symbol is appended';
    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const bundle = getLoadedUiLanguageTranslations(language);
      expect(bundle, language).toBeTruthy();
      const serialized = JSON.stringify(bundle);
      expect(serialized, language).not.toContain(marker);
      expect(serialized, language).not.toContain('50000 is not a table ceiling');
    }
    expect(JSON.stringify(SOURCE_UI_TRANSLATIONS)).not.toContain(marker);
  });

  it('keeps catalog-description skill retrieval help out of extra-locale inventories', () => {
    const marker = 'How many catalog skills automatic SkillRouter may retrieve by description';
    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const bundle = getLoadedUiLanguageTranslations(language);
      expect(bundle, language).toBeTruthy();
      const serialized = JSON.stringify(bundle);
      expect(serialized, language).not.toContain('AGENT_SKILL_RETRIEVAL_K');
      expect(serialized, language).not.toContain(marker);
    }
    expect(Object.keys(SOURCE_UI_TRANSLATIONS).join('\n')).not.toContain('AGENT_SKILL_RETRIEVAL_K');
  });

  it('keeps red-team second-opinion help out of extra-locale inventories', () => {
    const marker = 'Run one tool-free post-Decision red-team review on Native Multi full/specialist analysis.';
    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const bundle = getLoadedUiLanguageTranslations(language);
      expect(bundle, language).toBeTruthy();
      const serialized = JSON.stringify(bundle);
      expect(serialized, language).not.toContain('AGENT_RED_TEAM_ENABLED');
      expect(serialized, language).not.toContain(marker);
    }
    expect(Object.keys(SOURCE_UI_TRANSLATIONS).join('\n')).not.toContain('AGENT_RED_TEAM_ENABLED');
  });

  it('keeps settings-help examples out of the English inventory and locale bundles', () => {
    const inventoryHits = UI_TRANSLATION_KEYS.filter((key) => EXAMPLES_KEY_PATTERN.test(key));
    expect(inventoryHits).toEqual([]);

    const sourceHits = Object.keys(SOURCE_UI_TRANSLATIONS).filter((key) => EXAMPLES_KEY_PATTERN.test(key));
    expect(sourceHits).toEqual([]);

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const bundle = getLoadedUiLanguageTranslations(language);
      expect(bundle).toBeTruthy();
      const hits = Object.keys(bundle!).filter((key) => EXAMPLES_KEY_PATTERN.test(key));
      expect(hits, language).toEqual([]);
    }
  });

  it('exposes representative examples unchanged for zh, en, and an additional language', () => {
    const helpKey = 'settings.system.LOCAL_RUNTIME_AUTO_DETECT';
    const expected = settingsHelpEnUS[helpKey]?.examples;
    expect(expected?.length).toBeGreaterThan(0);
    expect(settingsHelpZhCN[helpKey]?.examples).toEqual(expected);

    for (const language of ['zh', 'en', 'ja'] as const) {
      const content = getSettingsHelpContent(helpKey, undefined, language);
      expect(content?.examples).toEqual(expected);
    }
  });

  it('keeps zh/en example arrays byte-for-byte equal for every settings-help entry that defines them', () => {
    for (const [key, enEntry] of Object.entries(settingsHelpEnUS)) {
      if (!enEntry?.examples) continue;
      expect(settingsHelpZhCN[key]?.examples, key).toEqual(enEntry.examples);
    }
  });

  it('fails parity validation when Chinese examples diverge from English', () => {
    const english = {
      'settings.demo.KEY': {
        title: 'Demo',
        examples: ['DEMO=true'],
      },
    };
    const chinese = {
      'settings.demo.KEY': {
        title: '演示',
        examples: ['DEMO=false'],
      },
    };
    expect(() => assertSettingsHelpExamplesParity(english, chinese)).toThrow(/byte-for-byte/i);
  });
});
