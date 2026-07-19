// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';
import { UI_TEXT, type UiLanguage } from '../../i18n/uiText';
import { ADDITIONAL_UI_LANGUAGES, UI_LANGUAGES } from '../../i18n/uiLanguages';
import {
  getLoadedUiLanguageTranslations,
  SOURCE_UI_TRANSLATIONS,
  UI_TRANSLATION_KEYS,
} from '../../i18n/translations';
import { getRegisteredUiTranslationKeys } from '../../i18n/createUiLanguageRecord';
import { ALERT_FORM_TEXT, ALERT_LIST_TEXT, ALERT_PAGE_TEXT, ALERT_TRIGGER_TEXT } from '../alerts';
import { BACKTEST_TEXT } from '../backtest';
import { PORTFOLIO_TEXT } from '../portfolio';
import {
  ANALYSIS_CONTEXT_CONTENT_TEXT,
  MARKET_REVIEW_CONTENT_TEXT,
  MARKET_STRUCTURE_CONTENT_TEXT,
  REPORT_NEWS_CONTENT_TEXT,
} from '../reportContent';
import { REPORT_CHROME_TEXT } from '../reportChrome';
import { SCREENING_TEXT } from '../screening';
import { SETTINGS_CONTROLS_TEXT } from '../settingsControls';
import { SETTINGS_MISC_TEXT } from '../settingsMisc';
import {
  MODEL_ACCESS_EDITOR_TEXT,
  MODEL_ACCESS_ERROR_LABELS,
  MODEL_ACCESS_ISSUES,
  MODEL_ACCESS_REASON_HINTS,
  MODEL_ACCESS_STAGE_LABELS,
  MODEL_ACCESS_TEXT,
  MODEL_ACCESS_TROUBLESHOOTING,
} from '../settingsModelAccess';
import { SETTINGS_NOTIFICATION_TEXT } from '../settingsNotifications';
import { SETTINGS_PAGE_TEXT } from '../settingsPage';
import { SETTINGS_WIZARD_TEXT } from '../settingsWizard';
import { STOCK_SEARCH_TEXT } from '../stockSearch';

type LocaleMap = Record<UiLanguage, unknown>;

const WESTERN_UI_LANGUAGES = ['de', 'es', 'ms', 'fr', 'id'] as const;
type WesternUiLanguage = (typeof WESTERN_UI_LANGUAGES)[number];

const registries: Record<string, LocaleMap> = {
  ui: UI_TEXT,
  alertsForm: ALERT_FORM_TEXT,
  alertsList: ALERT_LIST_TEXT,
  alertsPage: ALERT_PAGE_TEXT,
  alertsTrigger: ALERT_TRIGGER_TEXT,
  backtest: BACKTEST_TEXT,
  portfolio: PORTFOLIO_TEXT,
  reportChrome: REPORT_CHROME_TEXT,
  screening: SCREENING_TEXT,
  settingsControls: SETTINGS_CONTROLS_TEXT,
  settingsMisc: SETTINGS_MISC_TEXT,
  settingsModelAccess: MODEL_ACCESS_TEXT,
  settingsModelEditor: MODEL_ACCESS_EDITOR_TEXT,
  settingsModelErrors: MODEL_ACCESS_ERROR_LABELS,
  settingsModelIssues: MODEL_ACCESS_ISSUES,
  settingsModelReasons: MODEL_ACCESS_REASON_HINTS,
  settingsModelStages: MODEL_ACCESS_STAGE_LABELS,
  settingsModelTroubleshooting: MODEL_ACCESS_TROUBLESHOOTING,
  settingsNotifications: SETTINGS_NOTIFICATION_TEXT,
  settingsPage: SETTINGS_PAGE_TEXT,
  settingsWizard: SETTINGS_WIZARD_TEXT,
  stockSearch: STOCK_SEARCH_TEXT,
};

const reportRegistries = {
  reportAnalysisContext: ANALYSIS_CONTEXT_CONTENT_TEXT,
  reportMarketReview: MARKET_REVIEW_CONTENT_TEXT,
  reportMarketStructure: MARKET_STRUCTURE_CONTENT_TEXT,
  reportNewsContent: REPORT_NEWS_CONTENT_TEXT,
};

function flatten(value: unknown, prefix = ''): Map<string, string> {
  const result = new Map<string, string>();
  if (typeof value === 'string') {
    result.set(prefix, value);
    return result;
  }
  if (!value || typeof value !== 'object') {
    return result;
  }
  for (const [key, child] of Object.entries(value)) {
    const childPrefix = prefix ? `${prefix}.${key}` : key;
    for (const [childKey, text] of flatten(child, childPrefix)) {
      result.set(childKey, text);
    }
  }
  return result;
}

function placeholders(value: string): string[] {
  return Array.from(value.matchAll(/\{([A-Za-z0-9_]+)\}/g), (match) => match[1]).sort();
}

type UiTranslationKey = (typeof UI_TRANSLATION_KEYS)[number];
type UiTranslationBundle = Readonly<Record<UiTranslationKey, string>>;

function expectSemanticTranslation(
  translations: UiTranslationBundle,
  key: UiTranslationKey,
  required: RegExp,
  forbidden?: RegExp,
): void {
  const localized = translations[key];
  expect(localized, `required semantics: ${key}`).toMatch(required);
  if (forbidden) expect(localized, `forbidden semantics: ${key}`).not.toMatch(forbidden);
  expect(placeholders(localized), `reviewed placeholder mismatch: ${key}`).toEqual(
    placeholders(SOURCE_UI_TRANSLATIONS[key]),
  );
}

const STABLE_TECHNICAL_LITERAL_PATTERN = /`[^`]+`|https?:\/\/[^\s)]+|--[a-z][a-z0-9-]*|(?<![A-Za-z0-9])\.env(?:\.[a-z0-9_-]+)?\b|(?<![A-Za-z0-9_])[A-Z][A-Z0-9]*(?:_(?:<[A-Z][A-Z0-9_-]*>|[A-Z0-9]+))+(?:\([A-Z]+\))?(?![A-Za-z0-9_])|(?<![\p{L}\p{N}_.-])(?:(?:\.{1,2}\/)(?:[A-Za-z0-9._-]+\/)*[A-Za-z0-9._-]*[A-Za-z0-9_-]|\/[a-z][A-Za-z0-9._-]*\/(?:[A-Za-z0-9._-]+\/)*[A-Za-z0-9._-]*[A-Za-z0-9_-])|\b[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*_[a-z0-9_]+\b|\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b|\b(?:true|false|DEBUG|INFO|WARNING|ERROR|CRITICAL|YAML|JSON|API|CLI|LLM|HMAC|SSL|SSE|CSV|DNS|HTTP|HTTPS|TLS|ROE|FX)(?:s)?\b/gu;
const EXACT_CONFIG_LITERAL_PATTERN = /--[a-z][a-z0-9-]*|(?<![A-Za-z0-9])\.env(?:\.[a-z0-9_-]+)?\b|(?<![A-Za-z0-9_])[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+(?![A-Za-z0-9_])/gu;
const CONTEXTUAL_STABLE_LITERALS_BY_KEY = new Map<string, readonly string[]>([
  ['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.AGENT_ARCH.notes.0', ['multi']],
  ['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.AGENT_ARCH.usage', ['single', 'multi']],
  ['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.AGENT_ARCH.valueNotes.0', ['single']],
  ['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.AGENT_ARCH.valueNotes.1', ['multi']],
  ['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.AGENT_MODE.valueNotes.1', ['single', 'multi']],
  ['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.AGENT_ORCHESTRATOR_MODE.notes.0', ['multi']],
  ['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.AGENT_ORCHESTRATOR_MODE.summary', ['multi']],
  [
    'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.AGENT_ORCHESTRATOR_MODE.usage',
    ['quick', 'standard', 'full', 'specialist', 'full'],
  ],
  ['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.AGENT_ORCHESTRATOR_MODE.valueNotes.1', ['specialist']],
  ['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.AGENT_SKILL_ROUTING.usage', ['auto', 'manual']],
  ['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.AGENT_SKILL_ROUTING.valueNotes.0', ['auto', 'bull', 'bear', 'range']],
  [
    'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.context_compression.valueNotes.0',
    ['cost', 'balanced', 'long_context_raw_first'],
  ],
  [
    'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.data_source.TICKFLOW_KLINE_ADJUST.usage',
    ['none', 'forward', 'backward', 'forward_additive', 'backward_additive'],
  ],
  ['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.data_source.TICKFLOW_KLINE_ADJUST.valueNotes.0', ['none']],
  [
    'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.ai_model.LLM_CONFIG_MODE.usage',
    ['auto', 'YAML', 'Channels', 'legacy', 'channels', 'yaml', 'legacy'],
  ],
  ['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.ai_model.LLM_CONFIG_MODE.valueNotes.0', ['auto']],
  [
    'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.ai_model.LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL.usage',
    ['off', 'basic', 'debug', 'off'],
  ],
  [
    'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.ai_model.LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL.valueNotes.0',
    ['basic'],
  ],
  [
    'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.ai_model.LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL.valueNotes.1',
    ['debug'],
  ],
  [
    'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.market_review.valueNotes.0',
    ['cn', 'hk', 'us', 'jp', 'kr', 'both', 'cn', 'hk', 'us', 'jp', 'kr'],
  ],
  ['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.market_review.valueNotes.1', ['cn', 'us', 'jp']],
  [
    'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.notification.report_output.usage',
    ['simple', 'full', 'brief', 'zh', 'en'],
  ],
]);

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function orderedContextualStableLiterals(value: string, key: string): string[] {
  const literals = CONTEXTUAL_STABLE_LITERALS_BY_KEY.get(key) ?? [];
  const matches: string[] = [];
  let cursor = 0;
  for (const literal of literals) {
    const pattern = new RegExp(`(?<![A-Za-z0-9_])${escapeRegExp(literal)}(?![A-Za-z0-9_])`, 'g');
    pattern.lastIndex = cursor;
    const match = pattern.exec(value);
    if (!match) break;
    matches.push(match[0]);
    cursor = match.index + match[0].length;
  }
  return matches;
}

function literalOccurrenceCount(value: string, literal: string): number {
  const pattern = new RegExp(`(?<![A-Za-z0-9_])${escapeRegExp(literal)}(?![A-Za-z0-9_])`, 'g');
  return Array.from(value.matchAll(pattern)).length;
}

function stableTechnicalLiterals(value: string): string[] {
  return Array.from(value.matchAll(STABLE_TECHNICAL_LITERAL_PATTERN), (match) => {
    const literal = match[0].startsWith('`') ? match[0].slice(1, -1) : match[0];
    return /^(?:YAML|JSON|API|CLI|LLM|HMAC|SSL|SSE|CSV|DNS|HTTP|HTTPS|TLS|ROE|FX)s$/u.test(literal)
      ? literal.slice(0, -1)
      : literal;
  }).sort();
}

function missingStableTechnicalLiterals(source: string, localized: string): string[] {
  const localizedLiterals = new Set(stableTechnicalLiterals(localized));
  return [...new Set(stableTechnicalLiterals(source))].filter((literal) => !localizedLiterals.has(literal));
}

function exactConfigLiterals(value: string): string[] {
  return Array.from(value.matchAll(EXACT_CONFIG_LITERAL_PATTERN), (match) => match[0]).sort();
}

function missingExactConfigLiterals(source: string, localized: string): string[] {
  const localizedLiterals = new Set(exactConfigLiterals(localized));
  return [...new Set(exactConfigLiterals(source))].filter((literal) => !localizedLiterals.has(literal));
}

const uiTranslationModuleLoaders = import.meta.glob('/src/**/*.{ts,tsx}');

function listSourceFiles(directory: string): string[] {
  const files: string[] = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (entry.name === '__tests__' || entry.name === 'translations') continue;
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...listSourceFiles(fullPath));
    else if (entry.name.endsWith('.ts') || entry.name.endsWith('.tsx')) files.push(fullPath);
  }
  return files;
}

describe('locale registries', () => {
  it.each(Object.entries(registries))('%s keeps every UI language complete and interpolation-aligned', (_, registry) => {
    const zh = flatten(registry.zh);
    for (const language of UI_LANGUAGES) {
      const localized = flatten(registry[language]);
      expect([...localized.keys()].sort(), `${language} key mismatch`).toEqual([...zh.keys()].sort());
      for (const key of zh.keys()) {
        expect(localized.get(key)?.trim(), `empty ${language} translation: ${key}`).not.toBe('');
        expect(placeholders(localized.get(key) ?? ''), `${language} placeholder mismatch: ${key}`).toEqual(placeholders(zh.get(key) ?? ''));
      }
    }
  });

  it.each(Object.entries(reportRegistries))('%s keeps separate zh/en/ko report content aligned', (_, registry) => {
    const zh = flatten(registry.zh);
    for (const language of ['zh', 'en', 'ko'] as const) {
      const localized = flatten(registry[language]);
      expect([...localized.keys()].sort()).toEqual([...zh.keys()].sort());
      for (const key of zh.keys()) {
        expect(localized.get(key)?.trim()).not.toBe('');
        expect(placeholders(localized.get(key) ?? '')).toEqual(placeholders(zh.get(key) ?? ''));
      }
    }
  });

  it('keeps every generated locale bundle complete, clean, and placeholder-aligned', () => {
    const expectedKeys = [...UI_TRANSLATION_KEYS].sort();
    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      expect(translations, `${language} bundle is loaded`).not.toBeNull();
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      expect(Object.keys(translations).sort(), `${language} bundle keys`).toEqual(expectedKeys);
      for (const key of UI_TRANSLATION_KEYS) {
        const source = SOURCE_UI_TRANSLATIONS[key];
        const localized = translations[key];
        expect(localized.trim(), `empty ${language} translation: ${key}`).not.toBe('');
        expect(localized.normalize('NFC'), `non-NFC ${language} translation: ${key}`).toBe(localized);
        expect(localized, `corrupted ${language} translation: ${key}`).not.toMatch(/ZXQ|\u200B|\u200C|\u200D|\uFEFF/u);
        expect(localized, `encoded HTML entity in ${language} translation: ${key}`).not.toMatch(/&(?:amp|quot|lt|gt);/u);
        expect(localized, `repeated token in ${language} translation: ${key}`).not.toMatch(/(\p{L}[\p{L}\p{M}\p{N}_-]*)(?:[\s,;:!?./*-]+\1){4,}/iu);
        expect(localized, `repeated character in ${language} translation: ${key}`).not.toMatch(/([^\s])\1{11,}/u);
        expect(localized.length, `extreme length growth in ${language} translation: ${key}`).toBeLessThanOrEqual(
          Math.max(240, source.length * 8),
        );
        expect(placeholders(localized), `${language} placeholder mismatch: ${key}`).toEqual(placeholders(source));
        if (language === 'zh-TW') {
          expect(
            missingExactConfigLiterals(source, localized),
            `${language} missing exact config literal: ${key}`,
          ).toEqual([]);
        } else {
          expect(
            missingStableTechnicalLiterals(source, localized),
            `${language} missing stable literal: ${key}`,
          ).toEqual([]);
          const contextualLiterals = CONTEXTUAL_STABLE_LITERALS_BY_KEY.get(key) ?? [];
          expect(
            orderedContextualStableLiterals(source, key),
            `contextual stable literal map drift: ${key}`,
          ).toEqual(contextualLiterals);
          for (const literal of new Set(contextualLiterals)) {
            const requiredCount = contextualLiterals.filter((candidate) => candidate === literal).length;
            expect(
              literalOccurrenceCount(localized, literal),
              `${language} contextual stable literal mismatch: ${key} (${literal})`,
            ).toBeGreaterThanOrEqual(requiredCount);
          }
        }
      }
    }
  }, 20_000);

  it('preserves real-time source identifiers and reviewed settings-search terminology', () => {
    const sourceIdentifiers = ['akshare_em', 'akshare_sina', 'efinance', 'tencent', 'tickflow', 'tushare'] as const;
    const expectedSearchPlaceholders: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string> = {
      'zh-TW': '搜尋…',
      ja: '検索…',
      ko: '검색…',
      de: 'Suchen…',
      es: 'Buscar…',
      ms: 'Cari…',
      fr: 'Rechercher…',
      id: 'Cari…',
    };
    const mistranslatedQuoteTerms = /名言|인용구|Zitate|Citas|Citations|Petikan|Kutipan/u;
    const sourceKeyPrefix = 'utils.systemConfigI18n.fieldOptionLabelMaps.REALTIME_SOURCE_PRIORITY';

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      for (const identifier of sourceIdentifiers) {
        expect(
          translations[`${sourceKeyPrefix}.${identifier}`],
          `${language} real-time source identifier: ${identifier}`,
        ).toMatch(new RegExp(`\\(${identifier}\\)$`, 'u'));
      }
      expect(
        translations['locales.settingsControls.SETTINGS_CONTROLS_TEXT.searchOptionsPlaceholder'],
      ).toBe(expectedSearchPlaceholders[language]);
      expect(translations[`${sourceKeyPrefix}.tencent`]).not.toMatch(mistranslatedQuoteTerms);
    }
  });

  it('keeps reviewed market, broker, screening, and log terminology stable', () => {
    const expectedMarketLabels: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string> = {
      'zh-TW': '美股',
      ja: 'アメリカ合衆国',
      ko: '미국',
      de: 'USA',
      es: 'EE. UU.',
      ms: 'US',
      fr: 'États-Unis',
      id: 'US',
    };
    const marketKeys = [
      'i18n.uiText.UI_TEXT.decisionSignals.market.us',
      'locales.alerts.ALERT_MARKET_REGION_LABELS.us',
      'locales.stockSearch.STOCK_SEARCH_TEXT.marketUS',
    ] as const;
    const forbiddenSemanticErrors = /宇宙波背景|上映|상영|Vorführung|Proyección|Projection|Tayangan|Pemutaran|丸太|통나무|Stämme|troncos|balak|troncs|batang kayu/iu;
    const screeningMistranslations: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp>> = {
      ja: /在庫|審査/u,
      ko: /재고|심사/u,
      de: /Bildschirm/iu,
      es: /\b(?:pantalla|protección)\b/iu,
      ms: /\bpemeriksaan\b/iu,
      fr: /\b(?:dépistage|écran)\b/iu,
    };

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      for (const key of marketKeys) {
        expect(translations[key]).toBe(expectedMarketLabels[language]);
      }
      expect(translations['utils.portfolioFormat.BROKER_FALLBACK_NAMES.cmb']).toBe(
        language === 'zh-TW' ? '招商' : 'CMB',
      );
      for (const region of ['both', 'cn', 'hk', 'us', 'jp', 'kr'] as const) {
        expect(
          translations[`utils.systemConfigI18n.fieldOptionLabelMaps.MARKET_REVIEW_REGION.${region}`],
        ).toContain(`(${region})`);
      }
      expect(translations['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.LOG_LEVEL.usage']).not.toMatch(
        forbiddenSemanticErrors,
      );
      const screeningPattern = screeningMistranslations[language];
      if (screeningPattern) {
        for (const key of UI_TRANSLATION_KEYS.filter((candidate) => /screening|alphasift/iu.test(candidate))) {
          expect(translations[key], `${language} physical screening mistranslation: ${key}`).not.toMatch(
            screeningPattern,
          );
        }
      }
      for (const key of [
        'locales.screening.SCREENING_TEXT.completed',
        'locales.screening.SCREENING_TEXT.results',
        'locales.screening.SCREENING_TEXT.running',
        'locales.screening.SCREENING_TEXT.screening',
        'utils.taskMessage.TASK_MESSAGE_TEXT.task.screening.processing',
      ] as const) {
        expect(translations[key], `${language} semantic screening term: ${key}`).not.toMatch(forbiddenSemanticErrors);
      }
    }
  });

  it('keeps alert directions in the financial threshold domain', () => {
    const mistranslatedDirectionTerms = /皇帝|下着|着て|壊れ|황제|입고|착용|부서|Kaiser|getragen|tragen|gebrochen|emperador|llev[aá]ndola|desgastado|Maharaja|memakainya|dipakai|patah|empereur|porter sur|us[eé] en dessous|Kaisar/iu;
    const expectedOptions: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], {
      price: [string, string];
      threshold: [string, string];
      change: [string, string];
      cross: [string, string];
    }> = {
      'zh-TW': {
        price: ['向上突破', '向下跌破'], threshold: ['向上穿越', '向下穿越'], change: ['上漲達', '下跌達'], cross: ['金叉', '死叉'],
      },
      ja: {
        price: ['上抜け', '下抜け'], threshold: ['上抜け', '下抜け'], change: ['指定率以上上昇', '指定率以上下落'], cross: ['ゴールデンクロス', 'デッドクロス'],
      },
      ko: {
        price: ['상향 돌파', '하향 돌파'], threshold: ['상향 돌파', '하향 돌파'], change: ['지정 비율 이상 상승', '지정 비율 이상 하락'], cross: ['골든크로스', '데드크로스'],
      },
      de: {
        price: ['Überschreitet nach oben', 'Unterschreitet nach unten'], threshold: ['Überschreitet nach oben', 'Unterschreitet nach unten'], change: ['Steigt um', 'Fällt um'], cross: ['Bullische Kreuzung', 'Bärische Kreuzung'],
      },
      es: {
        price: ['Cruza al alza', 'Cruza a la baja'], threshold: ['Cruza al alza', 'Cruza a la baja'], change: ['Sube un', 'Baja un'], cross: ['Cruce alcista', 'Cruce bajista'],
      },
      ms: {
        price: ['Menembusi ke atas', 'Menembusi ke bawah'], threshold: ['Melintasi ke atas', 'Melintasi ke bawah'], change: ['Naik sebanyak', 'Turun sebanyak'], cross: ['Persilangan menaik', 'Persilangan menurun'],
      },
      fr: {
        price: ['Franchit à la hausse', 'Franchit à la baisse'], threshold: ['Franchit à la hausse', 'Franchit à la baisse'], change: ['Augmente de', 'Baisse de'], cross: ['Croisement haussier', 'Croisement baissier'],
      },
      id: {
        price: ['Menembus ke atas', 'Menembus ke bawah'], threshold: ['Melintasi ke atas', 'Melintasi ke bawah'], change: ['Naik sebesar', 'Turun sebesar'], cross: ['Persilangan bullish', 'Persilangan bearish'],
      },
    };
    const expectedPriceCross: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string> = {
      'zh-TW': '價格穿越',
      ja: '価格の閾値クロス',
      ko: '가격 임계값 교차',
      de: 'Preisübergang',
      es: 'Cruce de precios',
      ms: 'Lintasan harga',
      fr: 'Franchissement des prix',
      id: 'Persilangan harga',
    };
    const directionKeys = UI_TRANSLATION_KEYS.filter((key) => (
      key.startsWith('locales.alerts.ALERT_DIRECTION_LABELS.')
      || key.startsWith('locales.alerts.ALERT_PRICE_DIRECTION_OPTIONS.')
      || key.startsWith('locales.alerts.ALERT_THRESHOLD_DIRECTION_OPTIONS.')
      || key.startsWith('locales.alerts.ALERT_CHANGE_DIRECTION_OPTIONS.')
      || key.startsWith('locales.alerts.ALERT_CROSS_DIRECTION_OPTIONS.')
    ));

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      for (const key of directionKeys) {
        expect(translations[key], `${language} non-financial alert direction: ${key}`).not.toMatch(
          mistranslatedDirectionTerms,
        );
      }
      expect({
        price: [
          translations['locales.alerts.ALERT_PRICE_DIRECTION_OPTIONS.0.label'],
          translations['locales.alerts.ALERT_PRICE_DIRECTION_OPTIONS.1.label'],
        ],
        threshold: [
          translations['locales.alerts.ALERT_THRESHOLD_DIRECTION_OPTIONS.0.label'],
          translations['locales.alerts.ALERT_THRESHOLD_DIRECTION_OPTIONS.1.label'],
        ],
        change: [
          translations['locales.alerts.ALERT_CHANGE_DIRECTION_OPTIONS.0.label'],
          translations['locales.alerts.ALERT_CHANGE_DIRECTION_OPTIONS.1.label'],
        ],
        cross: [
          translations['locales.alerts.ALERT_CROSS_DIRECTION_OPTIONS.0.label'],
          translations['locales.alerts.ALERT_CROSS_DIRECTION_OPTIONS.1.label'],
        ],
      }).toEqual(expectedOptions[language]);
      expect(translations['locales.alerts.ALERT_PRICE_DIRECTION_OPTIONS.0.label']).not.toBe(
        translations['locales.alerts.ALERT_PRICE_DIRECTION_OPTIONS.1.label'],
      );
      expect(translations['locales.alerts.ALERT_CHANGE_DIRECTION_OPTIONS.0.label']).not.toBe(
        translations['locales.alerts.ALERT_CHANGE_DIRECTION_OPTIONS.1.label'],
      );
      expect([
        translations['locales.alerts.ALERT_SYMBOL_TYPE_OPTIONS.0.label'],
        translations['locales.alerts.ALERT_TYPE_FILTER_OPTIONS.1.label'],
        translations['locales.alerts.ALERT_TYPE_LABELS.price_cross'],
      ]).toEqual(Array(3).fill(expectedPriceCross[language]));
    }
  });

  it('keeps reviewed Settings option labels in their configuration domains', () => {
    const expectedOptions: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], {
      autoRouting: string;
      manualRouting: string;
      greenUp: string;
      redUp: string;
    }> = {
      'zh-TW': {
        autoRouting: '自動（按市場狀態）',
        manualRouting: '手動（使用 AGENT_SKILLS）',
        greenUp: '綠漲紅跌',
        redUp: '紅漲綠跌',
      },
      ja: {
        autoRouting: '自動（市場局面に基づく）',
        manualRouting: '手動（AGENT_SKILLS を使用）',
        greenUp: '上昇は緑／下落は赤',
        redUp: '上昇は赤／下落は緑',
      },
      ko: {
        autoRouting: '자동(시장 국면 기반)',
        manualRouting: '수동(AGENT_SKILLS 사용)',
        greenUp: '상승 초록 / 하락 빨강',
        redUp: '상승 빨강 / 하락 초록',
      },
      de: {
        autoRouting: 'Automatisch (nach Marktregime)',
        manualRouting: 'Manuell (AGENT_SKILLS verwenden)',
        greenUp: 'Anstieg grün / Rückgang rot',
        redUp: 'Anstieg rot / Rückgang grün',
      },
      es: {
        autoRouting: 'Automático (según el régimen de mercado)',
        manualRouting: 'Manual (uso AGENT_SKILLS)',
        greenUp: 'Subidas en verde / bajadas en rojo',
        redUp: 'Subidas en rojo / bajadas en verde',
      },
      ms: {
        autoRouting: 'Automatik (berdasarkan keadaan pasaran)',
        manualRouting: 'Manual (gunakan AGENT_SKILLS)',
        greenUp: 'Naik hijau / turun merah',
        redUp: 'Naik merah / turun hijau',
      },
      fr: {
        autoRouting: 'Automatique (selon le régime de marché)',
        manualRouting: 'Manuel (utiliser AGENT_SKILLS)',
        greenUp: 'Hausse en vert / baisse en rouge',
        redUp: 'Hausse en rouge / baisse en vert',
      },
      id: {
        autoRouting: 'Otomatis (berdasarkan kondisi pasar)',
        manualRouting: 'Manual (gunakan AGENT_SKILLS)',
        greenUp: 'Naik hijau / turun merah',
        redUp: 'Naik merah / turun hijau',
      },
    };

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      const expected = expectedOptions[language];
      expect(translations['utils.systemConfigI18n.fieldOptionLabelMaps.AGENT_SKILL_ROUTING.auto']).toBe(
        expected.autoRouting,
      );
      expect(
        translations['utils.systemConfigI18n.fieldOptionLabelMaps.AGENT_SKILL_ROUTING.auto (regime-based)'],
      ).toBe(expected.autoRouting);
      expect(translations['utils.systemConfigI18n.fieldOptionLabelMaps.AGENT_SKILL_ROUTING.manual']).toBe(
        expected.manualRouting,
      );
      expect(
        translations['utils.systemConfigI18n.fieldOptionLabelMaps.AGENT_SKILL_ROUTING.manual (use agent_skills)'],
      ).toBe(expected.manualRouting);
      expect(
        translations['utils.systemConfigI18n.fieldOptionLabelMaps.MARKET_REVIEW_COLOR_SCHEME.green_up'],
      ).toBe(expected.greenUp);
      expect(
        translations['utils.systemConfigI18n.fieldOptionLabelMaps.MARKET_REVIEW_COLOR_SCHEME.green up / red down'],
      ).toBe(expected.greenUp);
      expect(
        translations['utils.systemConfigI18n.fieldOptionLabelMaps.MARKET_REVIEW_COLOR_SCHEME.red_up'],
      ).toBe(expected.redUp);
      expect(
        translations['utils.systemConfigI18n.fieldOptionLabelMaps.MARKET_REVIEW_COLOR_SCHEME.red up / green down'],
      ).toBe(expected.redUp);

      for (const claudeCodeKey of [
        'components.settings.aiTaskMatrix.BACKEND_LABELS.claude_code_cli',
        'utils.systemConfigI18n.fieldOptionLabelMaps.GENERATION_BACKEND.claude_code_cli',
      ] as const) {
        expect(translations[claudeCodeKey], `${language} Claude Code product name`).toContain('Claude Code CLI');
      }
    }

    const japaneseTranslations = getLoadedUiLanguageTranslations('ja');
    const koreanTranslations = getLoadedUiLanguageTranslations('ko');
    const spanishTranslations = getLoadedUiLanguageTranslations('es');
    const frenchTranslations = getLoadedUiLanguageTranslations('fr');
    const indonesianTranslations = getLoadedUiLanguageTranslations('id');
    if (!japaneseTranslations || !koreanTranslations || !spanishTranslations
      || !frenchTranslations || !indonesianTranslations) {
      throw new Error('reviewed locale bundle is not loaded');
    }
    expect(japaneseTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL.off']).toBe('オフ');
    expect(koreanTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL.off']).toBe('꺼짐');
    expect(spanishTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL.off']).toBe('Desactivado');
    expect(japaneseTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.LOG_LEVEL.critical']).toBe('重大');
    expect(japaneseTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.NOTIFICATION_MIN_SEVERITY.critical']).toBe('重大');
    expect(koreanTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.LOG_LEVEL.critical']).toBe('심각');
    expect(koreanTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.NOTIFICATION_MIN_SEVERITY.critical']).toBe('심각');
    expect(japaneseTranslations['locales.alerts.ALERT_SEVERITY_LABELS.critical']).toBe('重大');
    expect(koreanTranslations['locales.alerts.ALERT_SEVERITY_LABELS.critical']).toBe('심각');
    expect(japaneseTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.NEWS_STRATEGY_PROFILE.long']).toBe('長期（30日）');
    expect(japaneseTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.NEWS_STRATEGY_PROFILE.medium']).toBe('中期（7日）');
    expect(japaneseTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.NEWS_STRATEGY_PROFILE.short']).toBe('短期（3日）');
    expect(japaneseTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.NEWS_STRATEGY_PROFILE.ultra_short']).toBe('超短期（1日）');
    expect(koreanTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.NEWS_STRATEGY_PROFILE.long']).toBe('장기 (30일)');
    expect(koreanTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.NEWS_STRATEGY_PROFILE.medium']).toBe('중기 (7일)');
    expect(koreanTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.NEWS_STRATEGY_PROFILE.short']).toBe('단기 (3일)');
    expect(koreanTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.NEWS_STRATEGY_PROFILE.ultra_short']).toBe('초단기 (1일)');
    expect(indonesianTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.REPORT_LANGUAGE.en']).toBe('Bahasa Inggris');
    expect(indonesianTranslations['utils.systemConfigI18n.fieldOptionLabelMaps.REPORT_LANGUAGE.english']).toBe('Bahasa Inggris');
    expect(spanishTranslations['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.data_source.search_api_keys.usage']).toBe('Los campos multiclave utilizan comas en inglés.');
    expect(indonesianTranslations['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.data_source.search_api_keys.usage']).toBe('Bidang multi-kunci menggunakan koma bahasa Inggris.');
    expect(frenchTranslations['i18n.uiText.UI_TEXT.runFlow.edgeLabel.invoke']).toBe('Appel');
  });

  it('keeps reviewed financial and current-context terms in their product domains', () => {
    const expected: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], {
      bullish: string;
      currentLanguage: string;
      currentStock: string;
      flat: string;
      hold: string;
      stockSearchIndex: string;
    }> = {
      'zh-TW': { bullish: '偏多', currentLanguage: '中文', currentStock: '目前股票：{stock}', flat: '持平', hold: '持有', stockSearchIndex: '股票搜尋索引遠端更新' },
      ja: { bullish: '強気', currentLanguage: '日本語', currentStock: '現在の銘柄：{stock}', flat: 'フラット', hold: 'ホールド', stockSearchIndex: '銘柄検索インデックスのリモート更新' },
      ko: { bullish: '강세', currentLanguage: '한국어', currentStock: '현재 종목: {stock}', flat: '보합', hold: '보유', stockSearchIndex: '종목 검색 인덱스 원격 업데이트' },
      de: { bullish: 'Bullisch', currentLanguage: 'Deutsch', currentStock: 'Aktuelle Aktie: {stock}', flat: 'Seitwärts', hold: 'Halten', stockSearchIndex: 'Remote-Updates des Aktiensuchindex' },
      es: { bullish: 'Alcista', currentLanguage: 'Español', currentStock: 'Acción actual: {stock}', flat: 'Sin cambios', hold: 'Mantener', stockSearchIndex: 'Actualizaciones remotas del índice de búsqueda de acciones' },
      ms: { bullish: 'Menaik', currentLanguage: 'Bahasa Melayu', currentStock: 'Saham semasa: {stock}', flat: 'Mendatar', hold: 'Pegang', stockSearchIndex: 'Kemas Kini Jarak Jauh Indeks Carian Saham' },
      fr: { bullish: 'Haussier', currentLanguage: 'Français', currentStock: 'Action actuelle : {stock}', flat: 'Stable', hold: 'Conserver', stockSearchIndex: 'Mises à jour distantes de l’index de recherche d’actions' },
      id: { bullish: 'Bullish', currentLanguage: 'Bahasa Indonesia', currentStock: 'Saham saat ini: {stock}', flat: 'Datar', hold: 'Tahan', stockSearchIndex: 'Pembaruan jarak jauh indeks pencarian saham' },
    };
    const stockSearchFailureMarker: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string> = {
      'zh-TW': '不會阻斷',
      ja: 'ブロックされません',
      ko: '차단되지 않습니다',
      de: 'blockieren weder',
      es: 'no bloquean',
      ms: 'tidak menyekat',
      fr: 'ne bloquent ni',
      id: 'tidak memblokir',
    };

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      const terms = expected[language];
      expect(translations['i18n.uiText.UI_TEXT.decisionSignals.timelineFamilyBullish']).toBe(terms.bullish);
      expect(translations['i18n.uiText.UI_TEXT.history.actionHold']).toBe(terms.hold);
      expect(translations['i18n.uiText.UI_TEXT.language.current']).toBe(terms.currentLanguage);
      expect(translations['i18n.uiText.UI_TEXT.decisionSignals.stockContextCurrent']).toBe(terms.currentStock);
      expect(translations['locales.backtest.BACKTEST_DIRECTION_EXPECTED_LABELS.flat']).toBe(terms.flat);
      expect(translations['locales.backtest.BACKTEST_MOVEMENT_LABELS.flat']).toBe(terms.flat);
      expect(translations['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.data_source.stock_index_remote.title']).toBe(
        terms.stockSearchIndex,
      );
      expect(translations['utils.systemConfigI18n.fieldTitleMaps.STOCK_INDEX_REMOTE_UPDATE_ENABLED']).toBe(
        terms.stockSearchIndex,
      );
      expect(
        translations['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.data_source.stock_index_remote.valueNotes.1'],
      ).toContain(stockSearchFailureMarker[language]);
    }
  });

  it('keeps market phases and price movements in their financial domains', () => {
    const expected: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], {
      directionUp: string;
      intraday: string;
      movementDown: string;
      movementUp: string;
      postmarket: string;
      premarket: string;
    }> = {
      'zh-TW': { directionUp: '看漲', intraday: '盤中', movementDown: '下跌', movementUp: '上漲', postmarket: '盤後', premarket: '盤前' },
      ja: { directionUp: '強気', intraday: '日中', movementDown: '下落', movementUp: '上昇', postmarket: '市場後', premarket: 'プレマーケット' },
      ko: { directionUp: '강세', intraday: '장중', movementDown: '하락', movementUp: '상승', postmarket: '장 마감 후', premarket: '장 시작 전' },
      de: { directionUp: 'Bullisch', intraday: 'Intraday', movementDown: 'Rückgang', movementUp: 'Anstieg', postmarket: 'Nachbörslich', premarket: 'Vorbörslich' },
      es: { directionUp: 'Alcista', intraday: 'Intradía', movementDown: 'Bajada', movementUp: 'Subida', postmarket: 'Posmercado', premarket: 'Premercado' },
      ms: { directionUp: 'Menaik harga', intraday: 'Intrahari', movementDown: 'Turun', movementUp: 'Naik', postmarket: 'Pasca pasaran', premarket: 'Pra-pasaran' },
      fr: { directionUp: 'Haussier', intraday: 'Intrajournalier', movementDown: 'Baisse', movementUp: 'Hausse', postmarket: 'Après-bourse', premarket: 'Avant-bourse' },
      id: { directionUp: 'Bullish', intraday: 'Intrahari', movementDown: 'Turun', movementUp: 'Naik', postmarket: 'Pasca-pasar', premarket: 'Pra-pasar' },
    };
    const phaseKeys = {
      intraday: [
        'i18n.uiText.UI_TEXT.decisionSignals.marketPhase.intraday',
        'i18n.uiText.UI_TEXT.decisionSignals.horizon.intraday',
        'locales.backtest.BACKTEST_PHASE_FILTER_OPTIONS.2.label',
        'locales.backtest.BACKTEST_PHASE_LABELS.intraday',
        'utils.marketPhase.MARKET_PHASE_LABELS.intraday',
        'utils.marketPhase.REQUEST_PHASE_LABELS.intraday',
      ],
      postmarket: [
        'i18n.uiText.UI_TEXT.decisionSignals.marketPhase.postmarket',
        'locales.backtest.BACKTEST_PHASE_FILTER_OPTIONS.3.label',
        'locales.backtest.BACKTEST_PHASE_LABELS.postmarket',
        'utils.marketPhase.MARKET_PHASE_LABELS.postmarket',
        'utils.marketPhase.REQUEST_PHASE_LABELS.postmarket',
      ],
      premarket: [
        'i18n.uiText.UI_TEXT.decisionSignals.marketPhase.premarket',
        'locales.backtest.BACKTEST_PHASE_FILTER_OPTIONS.1.label',
        'locales.backtest.BACKTEST_PHASE_LABELS.premarket',
        'utils.marketPhase.MARKET_PHASE_LABELS.premarket',
        'utils.marketPhase.REQUEST_PHASE_LABELS.premarket',
      ],
    } as const;

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      const terms = expected[language];
      for (const phase of ['intraday', 'postmarket', 'premarket'] as const) {
        for (const key of phaseKeys[phase]) {
          expect(translations[key], `${language} ${phase} alias: ${key}`).toBe(terms[phase]);
        }
      }
      expect(translations['locales.backtest.BACKTEST_DIRECTION_EXPECTED_LABELS.up']).toBe(terms.directionUp);
      expect(translations['locales.backtest.BACKTEST_MOVEMENT_LABELS.up']).toBe(terms.movementUp);
      expect(translations['locales.backtest.BACKTEST_MOVEMENT_LABELS.down']).toBe(terms.movementDown);
    }
  });

  it('keeps WebUI host and port help explicit about restart-only rebinding', () => {
    const expectedTitles: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], {
      host: string;
      port: string;
    }> = {
      'zh-TW': { host: 'WebUI 監聽地址', port: 'WebUI 埠' },
      ja: { host: 'WebUI ホスト', port: 'WebUI ポート' },
      ko: { host: 'WebUI 호스트', port: 'WebUI 포트' },
      de: { host: 'WebUI-Host', port: 'WebUI-Port' },
      es: { host: 'Host de WebUI', port: 'Puerto de WebUI' },
      ms: { host: 'Hos WebUI', port: 'Port WebUI' },
      fr: { host: 'Hôte WebUI', port: 'Port WebUI' },
      id: { host: 'Host WebUI', port: 'Port WebUI' },
    };
    const noLiveRebindMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp> = {
      'zh-TW': /不會.*重新繫結/u,
      ja: /再バインド.*(?:ません|ない)/u,
      ko: /다시 바인딩(?:하지|되지) 않습니다/u,
      de: /bindet.*nicht (?:erneut|neu)/iu,
      es: /no vuelve a enlaz/iu,
      ms: /tidak akan mengikat semula/iu,
      fr: /ne (?:modifie|réassocie) pas/iu,
      id: /tidak (?:akan )?mengikat ulang/iu,
    };
    const helpKeys = [
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.WEBUI_HOST.valueNotes.1',
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.WEBUI_PORT.valueNotes.2',
    ] as const;

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      expect(translations['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.WEBUI_HOST.title'])
        .toBe(expectedTitles[language].host);
      expect(translations['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.WEBUI_PORT.title'])
        .toBe(expectedTitles[language].port);
      for (const key of helpKeys) {
        expect(translations[key], `${language} persisted environment: ${key}`).toContain('.env');
        expect(translations[key], `${language} WebUI/API process: ${key}`).toMatch(/WebUI-?\/API/u);
        expect(translations[key], `${language} no live rebind: ${key}`).toMatch(
          noLiveRebindMarkers[language],
        );
      }
    }
  });

  it('keeps reviewed disabled-state help explicit rather than describing closure', () => {
    const disabledMarker: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string> = {
      'zh-TW': '關閉',
      ja: '無効',
      ko: '비활성화',
      de: 'deaktiviert',
      es: 'desactiv',
      ms: 'dinyahdayakan',
      fr: 'désactiv',
      id: 'dinonaktifkan',
    };
    const reviewedDisabledKeys = [
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.ai_model.LLM_PROMPT_CACHE_TELEMETRY_ENABLED.usage',
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.report.MERGE_EMAIL_NOTIFICATION.notes.0',
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.report.REPORT_SHOW_LLM_MODEL.usage',
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.report.REPORT_SUMMARY_ONLY.usage',
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.report.SINGLE_STOCK_NOTIFY.usage',
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.SAVE_CONTEXT_SNAPSHOT.valueNotes.0',
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.TRADING_DAY_CHECK_ENABLED.notes.0',
    ] as const;

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      for (const key of reviewedDisabledKeys) {
        expect(translations[key].toLocaleLowerCase(), `${language} disabled semantics: ${key}`).toContain(
          disabledMarker[language],
        );
      }
    }
  });

  it('keeps reviewed negative LLM configuration errors semantically negative', () => {
    const expectedTitles: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string> = {
      'zh-TW': '尚未配置 LLM 模型',
      ja: 'LLMモデルが設定されていません',
      ko: 'LLM 모델이 구성되지 않았습니다',
      de: 'Kein LLM-Modell konfiguriert',
      es: 'No hay ningún modelo LLM configurado',
      ms: 'Tiada model LLM dikonfigurasikan',
      fr: 'Aucun modèle LLM n’est configuré',
      id: 'Tidak ada model LLM yang dikonfigurasi',
    };
    const remediationMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], readonly RegExp[]> = {
      'zh-TW': [/主要模型/u, /模型連線/u, /API Key/u, /再試/u],
      ja: [/プライマリモデル/u, /接続/u, /API キー/u, /もう一度/u],
      ko: [/기본 모델/u, /연결/u, /API 키/u, /다시/u],
      de: [/primäres Modell/iu, /Verbindung/iu, /API-Schlüssel/iu, /erneut/iu],
      es: [/modelo principal/iu, /conexión/iu, /clave API/iu, /vuelve a intentarlo/iu],
      ms: [/model utama/iu, /sambungan/iu, /kunci API/iu, /cuba lagi/iu],
      fr: [/modèle principal/iu, /connexion/iu, /clé API/iu, /réessayez/iu],
      id: [/model utama/iu, /koneksi/iu, /kunci API/iu, /coba lagi/iu],
    };
    const titleKey = 'api.error.GENERIC_ERROR_TEXT.llm_not_configured.title' as const;
    const messageKey = 'api.error.GENERIC_ERROR_TEXT.llm_not_configured.message' as const;

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      expect(translations[titleKey], `${language} LLM-not-configured title`).toBe(expectedTitles[language]);
      for (const marker of remediationMarkers[language]) {
        expect(translations[messageKey], `${language} LLM-not-configured remediation`).toMatch(marker);
      }
    }
  });

  it('preserves Markdown and AlphaSift as product literals in localized actions', () => {
    const expectedMarkdownSourceAction: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string> = {
      'zh-TW': '複製 Markdown 原始碼',
      ja: 'Markdownソースをコピー',
      ko: 'Markdown 소스 복사',
      de: 'Markdown-Quelle kopieren',
      es: 'Copiar fuente Markdown',
      ms: 'Salin sumber Markdown',
      fr: 'Copier la source Markdown',
      id: 'Salin sumber Markdown',
    };
    const markdownKeys = UI_TRANSLATION_KEYS.filter((key) => SOURCE_UI_TRANSLATIONS[key].includes('Markdown'));
    const alphaSiftKeys = UI_TRANSLATION_KEYS.filter((key) => SOURCE_UI_TRANSLATIONS[key].includes('AlphaSift'));

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      for (const key of markdownKeys) {
        expect(translations[key], `${language} Markdown literal: ${key}`).toContain('Markdown');
      }
      for (const key of alphaSiftKeys) {
        expect(translations[key], `${language} AlphaSift literal: ${key}`).toContain('AlphaSift');
      }
      expect(translations['locales.reportChrome.REPORT_CHROME_TEXT.copyMarkdownSource']).toBe(
        expectedMarkdownSourceAction[language],
      );
    }
  });

  it('does not leak reviewed source-language UI fragments into localized copy', () => {
    const reviewedEnglishLeaks = [
      { language: 'de', key: 'locales.alerts.ALERT_LIST_TEXT.enable', source: 'Enable' },
      { language: 'es', key: 'i18n.uiText.UI_TEXT.decisionSignals.outcome.unable', source: 'Unable' },
      { language: 'fr', key: 'locales.alerts.ALERT_TRIGGER_TEXT.dataTime', source: 'Data time' },
      { language: 'id', key: 'locales.portfolio.PORTFOLIO_TEXT.refreshData', source: 'Refresh data' },
    ] as const;

    for (const { language, key, source } of reviewedEnglishLeaks) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      expect(translations[key], `${language} untranslated UI copy: ${key}`).not.toBe(source);
    }

    const koreanTranslations = getLoadedUiLanguageTranslations('ko');
    if (!koreanTranslations) throw new Error('ko bundle is not loaded');
    expect(koreanTranslations['locales.alerts.ALERT_LIST_TEXT.enable']).toBe('활성화');

    const routingUsageKey = 'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.AGENT_NL_ROUTING.usage' as const;
    for (const language of ADDITIONAL_UI_LANGUAGES.filter((candidate) => candidate !== 'zh-TW')) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      expect(translations[routingUsageKey], `${language} Simplified Chinese bot term`).not.toContain('机器人');
    }
  });

  it('uses semantic stable keys for the settings information architecture', () => {
    const settingsArchitectureKeys = UI_TRANSLATION_KEYS.filter((key) => (
      key.startsWith('components.settings.settingsInformationArchitecture.SETTINGS_SECTIONS.')
    ));

    expect(settingsArchitectureKeys.length).toBeGreaterThan(0);
    expect(settingsArchitectureKeys.filter((key) => /\.\d+(?:\.|$)/u.test(key))).toEqual([]);
  });

  it('keeps a distinct per-field title catalog for every registered setting', () => {
    const fieldTitlePrefix = 'utils.systemConfigI18n.fieldTitleMaps.';
    const fieldTitleKeys = UI_TRANSLATION_KEYS.filter((key) => key.startsWith(fieldTitlePrefix));
    const identityKeys = [
      `${fieldTitlePrefix}EMAIL_SENDER`,
      `${fieldTitlePrefix}EMAIL_PASSWORD`,
      `${fieldTitlePrefix}EMAIL_RECEIVERS`,
      `${fieldTitlePrefix}OPENAI_MODEL`,
      `${fieldTitlePrefix}OPENAI_VISION_MODEL`,
    ] as const;

    expect(fieldTitleKeys.length).toBeGreaterThan(0);
    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      const localizedTitles = identityKeys.map((key) => translations[key]);
      expect(new Set(localizedTitles.slice(0, 3)).size, `${language} email field identities`).toBe(3);
      expect(localizedTitles[3], `${language} text model identity`).not.toBe(localizedTitles[4]);
      for (const key of identityKeys) {
        expect(translations[key], `${language} untranslated field title: ${key}`).not.toBe(
          SOURCE_UI_TRANSLATIONS[key],
        );
      }
    }
  });

  it('keeps smoke checks in the software-testing domain', () => {
    const smokeMistranslations: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp>> = {
      ja: /煙/u,
      ko: /연기/u,
      de: /\bRauch(?:test|lauf|erzeugungstest)?\b/iu,
      es: /\bhumo\b/iu,
      ms: /\basap\b/iu,
      fr: /\bfumée\b/iu,
      id: /\basap\b/iu,
    };
    const smokeKeys = UI_TRANSLATION_KEYS.filter((key) => /\bsmoke\b/iu.test(SOURCE_UI_TRANSLATIONS[key]));

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      const smokePattern = smokeMistranslations[language];
      if (!smokePattern) continue;
      for (const key of smokeKeys) {
        expect(translations[key], `${language} literal smoke mistranslation: ${key}`).not.toMatch(smokePattern);
      }
    }
  });

  it('keeps reviewed request errors and configuration help semantically stable', () => {
    const expectedTimeout: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string> = {
      'zh-TW': '請求超時',
      ja: 'リクエストがタイムアウトしました',
      ko: '요청 시간 초과',
      de: 'Zeitüberschreitung der Anfrage',
      es: 'Tiempo de espera agotado',
      ms: 'Permintaan tamat masa',
      fr: 'Délai de la requête dépassé',
      id: 'Waktu permintaan habis',
    };
    const expectedBlocked: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string> = {
      'zh-TW': '請求被攔截',
      ja: 'リクエストがブロックされました',
      ko: '요청 차단됨',
      de: 'Anfrage blockiert',
      es: 'Solicitud bloqueada',
      ms: 'Permintaan disekat',
      fr: 'Requête bloquée',
      id: 'Permintaan diblokir',
    };
    const capabilityTruthMistranslations: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp>> = {
      ja: /真実|真理/u,
      ko: /진실|진리/u,
      de: /Wahrheit/iu,
      es: /\bverdad(?:es)?\b/iu,
      ms: /\bkebenaran\b/iu,
      fr: /\bvérité(?:s)?\b/iu,
      id: /\bkebenaran\b/iu,
    };
    const webhookTransmissionMistranslations: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp>> = {
      ja: /送信|伝送|転送/u,
      ko: /전송|송신/u,
      de: /Übertragung/iu,
      es: /\btransmisi[oó]n\b/iu,
      ms: /\b(?:penghantaran|transmisi)\b/iu,
      fr: /\btransmission\b/iu,
      id: /\btransmisi\b/iu,
    };
    const duplicatedExternalTerm = /外部\s*外部|외부\s*외부|\b(exterior|external|externo|externa|externos|externas|externe|externes|luaran|eksternal)\b[\s,/-]+\1\b/iu;
    const capabilityUsageKey = 'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.llm_channel.capability_checks.usage';
    const webhookHelpKeys = [
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.notification.WEBHOOK_VERIFY_SSL.summary',
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.notification.WEBHOOK_VERIFY_SSL.impact.0',
    ] as const;

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      expect(translations['locales.settingsModelAccess.MODEL_ACCESS_ERROR_LABELS.timeout']).toBe(
        expectedTimeout[language],
      );
      expect(translations['locales.screening.SCREENING_TEXT.diagnosticTimeout']).toBe(expectedTimeout[language]);
      expect(translations['locales.settingsModelAccess.MODEL_ACCESS_ERROR_LABELS.request_blocked']).toBe(
        expectedBlocked[language],
      );
      const capabilityPattern = capabilityTruthMistranslations[language];
      if (capabilityPattern) {
        expect(translations[capabilityUsageKey], `${language} capability-check meaning`).not.toMatch(capabilityPattern);
      }
      const webhookPattern = webhookTransmissionMistranslations[language];
      if (webhookPattern) {
        for (const key of webhookHelpKeys) {
          expect(translations[key], `${language} webhook verification meaning: ${key}`).not.toMatch(webhookPattern);
        }
      }
      expect(
        translations['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.HTTP_PROXY.summary'],
        `${language} duplicated external proxy term`,
      ).not.toMatch(duplicatedExternalTerm);
    }
  });

  it('preserves proxy, security, startup, and OpenCode command contracts', () => {
    const proxyMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp> = {
      'zh-TW': /代理/u,
      ja: /プロキシ/u,
      ko: /프록시/u,
      de: /Proxy/iu,
      es: /\bproxy\b/iu,
      ms: /\bproksi\b/iu,
      fr: /\bproxy\b/iu,
      id: /\bproksi\b/iu,
    };
    const negativeMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp> = {
      'zh-TW': /不/u,
      ja: /ない|ません|(?:さ|せ)ず|ではなく/u,
      ko: /않|아니|하지/u,
      de: /\b(?:nicht|kein(?:e|en|er|em|es)?|ohne)\b/iu,
      es: /\b(?:no|sin)\b/iu,
      ms: /\b(?:tidak|jangan|bukan|tanpa)\b/iu,
      fr: /(?:\bne\b.*\bpas\b|n[’'][^.!?]*\bpas\b|\bsans\b)/iu,
      id: /\b(?:tidak|jangan|bukan|tanpa)\b/iu,
    };
    const marketReviewMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp> = {
      'zh-TW': /大盤覆盤|市場覆盤/u,
      ja: /市場レビュー/u,
      ko: /시장 (?:검토|리뷰)/u,
      de: /Markt(?:überprüfung|überblick|rückblick)/iu,
      es: /revisión de mercado/iu,
      ms: /ulasan pasaran/iu,
      fr: /revue de marché/iu,
      id: /tinjauan pasar/iu,
    };
    const proxyKeys = [
      'api.error.GENERIC_ERROR_TEXT.upstream_network.message',
      'locales.settingsModelAccess.MODEL_ACCESS_REASON_HINTS.dns_error',
      'locales.settingsModelAccess.MODEL_ACCESS_REASON_HINTS.tls_error',
      'locales.settingsModelAccess.MODEL_ACCESS_TROUBLESHOOTING.network_error',
    ] as const;
    const marketReviewKeys = [
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.ai_model.OPENCODE_CLI_MODEL.impact.0',
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.TRADING_DAY_CHECK_ENABLED.impact.0',
    ] as const;
    const physicalDiskReview = /ディスク|디스크|Festplatten?|\bdiscos?\b|\bdisques?\b|\bcakera\b|\bdisk\b/iu;

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      for (const key of proxyKeys) {
        expect(translations[key], `${language} proxy semantics: ${key}`).toMatch(proxyMarkers[language]);
      }
      for (const key of [
        'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.RUN_IMMEDIATELY.notes.0',
        'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.notification.WEBHOOK_VERIFY_SSL.notes.0',
      ] as const) {
        expect(translations[key], `${language} required negation: ${key}`).toMatch(negativeMarkers[language]);
      }
      expect(translations['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.notification.WEBHOOK_VERIFY_SSL.notes.0'])
        .toContain('SSL');
      expect(translations['locales.settingsHelp.SETTINGS_HELP_MAPS.settings.ai_model.OPENCODE_CLI_MODEL.examples.0'])
        .toBe('OPENCODE_CLI_MODEL=provider/model');
      const openCodeSummary = translations[
        'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.ai_model.OPENCODE_CLI_MODEL.summary'
      ];
      expect(openCodeSummary).toContain('OpenCode');
      expect(openCodeSummary).toContain('run');
      expect(openCodeSummary).toContain('--model');
      const openCodeUsage = translations[
        'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.ai_model.OPENCODE_CLI_MODEL.usage'
      ];
      expect(openCodeUsage).toContain('--model');
      expect(openCodeUsage, `${language} OpenCode flag omission`).toMatch(negativeMarkers[language]);
      const openCodeImpact = translations[
        'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.ai_model.OPENCODE_CLI_MODEL.impact.0'
      ];
      expect(openCodeImpact, `${language} ask-stock boundary`).toMatch(negativeMarkers[language]);
      expect(openCodeImpact, `${language} ask-stock boundary`).toMatch({
        'zh-TW': /問股助手/u,
        ja: /銘柄問い合わせアシスタント/u,
        ko: /종목 문의 도우미/u,
        de: /Aktienassistent/iu,
        es: /asistente de consulta de acciones/iu,
        ms: /pembantu pertanyaan saham/iu,
        fr: /assistant d’interrogation boursière/iu,
        id: /asisten tanya-saham/iu,
      }[language]);
      for (const key of marketReviewKeys) {
        expect(translations[key], `${language} market-review semantics: ${key}`).toMatch(
          marketReviewMarkers[language],
        );
        expect(translations[key], `${language} physical disk review: ${key}`).not.toMatch(physicalDiskReview);
      }
    }
  });

  it('keeps logout, call counts, and marked-setting errors action-oriented', () => {
    const logoutMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp> = {
      'zh-TW': /退出/u,
      ja: /ログアウト/u,
      ko: /로그아웃/u,
      de: /Abmeld/iu,
      es: /cerrar (?:la )?sesión|cierre de sesión/iu,
      ms: /Log keluar/iu,
      fr: /déconnect|déconnexion/iu,
      id: /Keluar/iu,
    };
    const expectedCalls: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string> = {
      'zh-TW': '{count} 次呼叫',
      ja: '{count} 回',
      ko: '{count}회 호출',
      de: '{count} Aufrufe',
      es: '{count} llamadas',
      ms: '{count} panggilan',
      fr: '{count} appels',
      id: '{count} panggilan',
    };
    const callDetailMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string> = {
      'zh-TW': '{calls} 次',
      ja: '{calls} 回',
      ko: '{calls}회 호출',
      de: '{calls} Aufrufe',
      es: '{calls} llamadas',
      ms: '{calls} panggilan',
      fr: '{calls} appels',
      id: '{calls} panggilan',
    };
    const totalCallMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp> = {
      'zh-TW': /呼叫/u,
      ja: /呼び出し/u,
      ko: /호출/u,
      de: /Aufruf/iu,
      es: /llamad/iu,
      ms: /panggilan/iu,
      fr: /appel/iu,
      id: /panggilan/iu,
    };
    const markedSettingMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp> = {
      'zh-TW': /標記/u,
      ja: /マークされた/u,
      ko: /표시된/u,
      de: /markierten/iu,
      es: /marcados/iu,
      ms: /ditandakan/iu,
      fr: /signalés/iu,
      id: /ditandai/iu,
    };
    const validationMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp> = {
      'zh-TW': /校驗|驗證/u,
      ja: /検証/u,
      ko: /검증/u,
      de: /Validierung/iu,
      es: /validación/iu,
      ms: /pengesahan/iu,
      fr: /validation/iu,
      id: /validasi/iu,
    };
    const missingInputMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp> = {
      'zh-TW': /或輸入/u,
      ja: /または入力値/u,
      ko: /또는 입력값/u,
      de: /oder eine Eingabe/iu,
      es: /o la entrada/iu,
      ms: /atau input/iu,
      fr: /ou la valeur saisie/iu,
      id: /atau input/iu,
    };

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      for (const key of [
        'i18n.uiText.UI_TEXT.layout.logout',
        'i18n.uiText.UI_TEXT.layout.logoutConfirm',
        'i18n.uiText.UI_TEXT.layout.logoutMessage',
        'i18n.uiText.UI_TEXT.layout.logoutTitle',
      ] as const) {
        expect(translations[key], `${language} logout action: ${key}`).toMatch(logoutMarkers[language]);
      }
      expect(translations['i18n.uiText.UI_TEXT.usage.calls']).toBe(expectedCalls[language]);
      const callTypeDetail = translations['i18n.uiText.UI_TEXT.usage.callTypeDetail'];
      expect(callTypeDetail).toContain(callDetailMarkers[language]);
      expect(placeholders(callTypeDetail)).toEqual(['calls', 'completion', 'prompt']);
      expect(translations['i18n.uiText.UI_TEXT.usage.totalCallsHint']).toMatch(totalCallMarkers[language]);
      expect(translations['api.error.STABLE_ERROR_TEXT.validation_failed.title']).toMatch(
        validationMarkers[language],
      );
      expect(translations['api.error.STABLE_ERROR_TEXT.validation_failed.message']).toMatch(
        markedSettingMarkers[language],
      );
      expect(translations['api.error.GENERIC_ERROR_TEXT.missing_params.message']).toMatch(
        missingInputMarkers[language],
      );
    }

    const japanese = getLoadedUiLanguageTranslations('ja');
    const korean = getLoadedUiLanguageTranslations('ko');
    if (!japanese || !korean) throw new Error('Japanese and Korean bundles must be loaded');
    expect(japanese['locales.settingsModelAccess.MODEL_ACCESS_TEXT.extraHeadersPlaceholder'])
      .toBe('JSON オブジェクトを入力するか、無効な値を消去してください。');
    expect(korean['locales.settingsModelAccess.MODEL_ACCESS_TEXT.extraHeadersPlaceholder'])
      .toBe('JSON 객체를 입력하거나 잘못된 값을 지우세요.');
    expect(japanese['locales.settingsModelAccess.MODEL_ACCESS_TEXT.extraHeaders'])
      .toBe('追加リクエストヘッダー（JSON）');
    expect(korean['locales.settingsModelAccess.MODEL_ACCESS_TEXT.extraHeaders'])
      .toBe('추가 요청 헤더(JSON)');
    expect(korean['api.error.GENERIC_ERROR_TEXT.upstream_timeout.title'])
      .toBe('업스트림 서비스 응답 시간이 초과되었습니다');
    for (const key of [
      'locales.settingsModelAccess.MODEL_ACCESS_EDITOR_TEXT.assignModels',
      'locales.settingsModelAccess.MODEL_ACCESS_TEXT.assignModels',
    ] as const) {
      expect(japanese[key]).toBe('タスクルーティングでモデルを割り当てる →');
      expect(korean[key]).toBe('작업 라우팅에서 모델 할당 →');
    }
  });

  it('keeps stock and execution terminology in the financial domain', () => {
    const stockInventoryTerms: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp>> = {
      ja: /在庫/u,
      ko: /재고/u,
      de: /\b(?:Lager|Bestand|Vorrat|Schäfte?)\b/iu,
      es: /\b(?:inventarios?|existencias|stocks?|culatas?)\b/iu,
      ms: /\bstok\b/iu,
      fr: /\b(?:stocks?|crosses?)\b/iu,
      id: /\bstok\b/iu,
    };
    const executionMistranslations: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp>> = {
      ja: /ラン位相|運転|走行|処刑|滑走路/u,
      ko: /활주로|런 토폴로지|도망|처형/u,
      de: /Lauffluss|Laufdurchfluss|Belastungslauffluss|Landebahn/u,
      es: /Flujo de (?:Carrera|aguas)|\bpista\b/iu,
      ms: /\blarian\b|\blandasan\b/iu,
      fr: /Écoulement de runes|Flux de course|Débit de course|\bpiste\b/iu,
      id: /\bBerlari\b|Alur Lari|landasan pacu/iu,
    };
    const expectedRunFlowEyebrows: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string>> = {
      'zh-TW': '執行流程',
      ja: '実行フロー',
      ko: '실행 흐름',
      de: 'AUSFÜHRUNGSABLAUF',
      es: 'FLUJO DE EJECUCIÓN',
      ms: 'ALIRAN PELAKSANAAN',
      fr: 'FLUX D’EXÉCUTION',
      id: 'ALUR EKSEKUSI',
    };
    const expectedLanguageToggle: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string>> = {
      'zh-TW': '切換介面語言',
      ja: 'UI言語を切り替える',
      ko: 'UI 언어 전환',
      de: 'UI-Sprache wechseln',
      es: 'Cambiar idioma de la interfaz',
      ms: 'Tukar bahasa antara muka',
      fr: 'Changer la langue de l’interface',
      id: 'Ganti bahasa antarmuka',
    };
    const runFlowMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp> = {
      'zh-TW': /執行流|執行流程/u,
      ja: /実行フロー/u,
      ko: /실행 흐름/u,
      de: /Ausführungsablauf/iu,
      es: /flujo de ejecución/iu,
      ms: /aliran pelaksanaan/iu,
      fr: /flux d’exécution/iu,
      id: /alur eksekusi/iu,
    };
    const runningStatusMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp> = {
      'zh-TW': /執行中/u,
      ja: /実行中/u,
      ko: /실행 중/u,
      de: /ausgeführt|Ausführung|läuft/iu,
      es: /ejecución|ejecutando/iu,
      ms: /sedang (?:berjalan|dilaksanakan)/iu,
      fr: /exécution|en cours/iu,
      id: /dieksekusi|dijalankan/iu,
    };

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      const stockPattern = stockInventoryTerms[language];
      if (stockPattern) {
        for (const key of UI_TRANSLATION_KEYS.filter((candidate) => /\bstocks?\b/iu.test(SOURCE_UI_TRANSLATIONS[candidate]))) {
          const reviewText = translations[key]
            .replace(/\{[A-Za-z0-9_]+\}/gu, '')
            .replace(/--[a-z][a-z0-9-]*/gu, '')
            .replace(/Stock Ask Assistant/gu, '');
          expect(reviewText, `${language} inventory mistranslation: ${key}`).not.toMatch(stockPattern);
        }
      }
      const executionPattern = executionMistranslations[language];
      if (executionPattern) {
        for (const key of UI_TRANSLATION_KEYS.filter((candidate) => (
          candidate.includes('.runFlow.')
          || /\.settings\.scheduler(?:NextRun|Running|RunningNow|RunNow)/u.test(candidate)
          || candidate === 'locales.reportChrome.REPORT_CHROME_TEXT.title'
          || /locales\.screening\.SCREENING_TEXT\.(?:run|runId|running)$/u.test(candidate)
        ))) {
          expect(translations[key], `${language} execution mistranslation: ${key}`).not.toMatch(executionPattern);
        }
      }
      expect(translations['i18n.uiText.UI_TEXT.runFlow.eyebrow']).toBe(expectedRunFlowEyebrows[language]);
      expect(translations['i18n.uiText.UI_TEXT.language.toggle']).toBe(expectedLanguageToggle[language]);
      for (const key of [
        'i18n.uiText.UI_TEXT.runFlow.errorTitle',
        'i18n.uiText.UI_TEXT.runFlow.loadingTitle',
      ] as const) {
        expect(translations[key], `${language} run-flow concept: ${key}`).toMatch(runFlowMarkers[language]);
      }
      expect(translations['i18n.uiText.UI_TEXT.runFlow.status.running']).toMatch(
        runningStatusMarkers[language],
      );
    }
  });

  it('keeps fold controls, screening, and drawdown terms in their UI and finance domains', () => {
    const physicalCollapseTerms: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp>> = {
      ja: /崩壊|倒壊/u,
      ko: /붕괴|무너지/u,
      de: /Zusammenbruch|Kollaps/iu,
      es: /Colapso|derrumbe/iu,
      ms: /keruntuhan|runtuh/iu,
      fr: /Effondrement/iu,
      id: /runtuh/iu,
    };
    const fermentationTerms: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp>> = {
      ja: /発酵/u,
      ko: /발효/u,
      de: /Fermentation/iu,
      es: /fermentación/iu,
      ms: /penapaian/iu,
      fr: /fermentation/iu,
      id: /fermentasi/iu,
    };
    const nonMarketQuoteTerms: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp>> = {
      ja: /引用/u,
      ko: /인용/u,
      de: /Angebot/iu,
      es: /Presupuesto/iu,
      ms: /Sebut harga/iu,
      fr: /Devis/iu,
      id: /Kutipan/iu,
    };
    const spoiledStaleTerms: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp>> = {
      ko: /탁하/u,
      de: /abgestanden/iu,
      es: /ranci/iu,
      ms: /basi/iu,
      fr: /rassis/iu,
      id: /basi/iu,
    };
    const expectedRecordCount: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string> = {
      'zh-TW': '記錄數',
      ja: 'レコード数',
      ko: '레코드 수',
      de: 'Datensätze',
      es: 'Registros',
      ms: 'Rekod',
      fr: 'Enregistrements',
      id: 'Catatan',
    };
    const expectedDrawdown: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string> = {
      'zh-TW': '組合回撤',
      ja: 'ポートフォリオドローダウン',
      ko: '포트폴리오 낙폭',
      de: 'Portfolio-Drawdown',
      es: 'Drawdown de cartera',
      ms: 'Susutan portfolio',
      fr: 'Repli du portefeuille',
      id: 'Drawdown portofolio',
    };
    const drawdownMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp> = {
      'zh-TW': /回撤/u,
      ja: /ドローダウン/u,
      ko: /낙폭/u,
      de: /Drawdown/iu,
      es: /drawdown|caída/iu,
      ms: /susutan/iu,
      fr: /repli/iu,
      id: /drawdown/iu,
    };
    const marketQuoteMarkers: Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp> = {
      'zh-TW': /行情/u,
      ja: /価格情報|株価/u,
      ko: /시세/u,
      de: /Kurs/iu,
      es: /cotizaci[oó]n(?:es)?/iu,
      ms: /harga/iu,
      fr: /cours/iu,
      id: /harga/iu,
    };
    const foldControlKeys = UI_TRANSLATION_KEYS.filter((key) => (
      /\bcollaps(?:e|ed)\b/iu.test(SOURCE_UI_TRANSLATIONS[key])
      && key !== 'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.TRUST_X_FORWARDED_FOR.valueNotes.0'
    ));
    const proxyConvergenceKey =
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.TRUST_X_FORWARDED_FOR.valueNotes.0' as const;
    const developmentKeys = [
      'locales.screening.SCREENING_TEXT.cachedHotspots',
      'locales.screening.SCREENING_TEXT.loadingHotspotDetail',
      'locales.screening.SCREENING_TEXT.routeTimeline',
      'locales.screening.SCREENING_TEXT.selectHotspot',
    ] as const;
    const marketQuoteKeys = [
      'locales.screening.SCREENING_TEXT.quotePending',
      'locales.screening.SCREENING_TEXT.resultsDescription',
      'locales.screening.SCREENING_TEXT.strategyDescription',
    ] as const;
    const rsiKeys = UI_TRANSLATION_KEYS.filter((key) => /\bRSI\b/u.test(SOURCE_UI_TRANSLATIONS[key]));
    const drawdownKeys = UI_TRANSLATION_KEYS.filter((key) => /\bdrawdown\b/iu.test(SOURCE_UI_TRANSLATIONS[key]));

    for (const language of ADDITIONAL_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      const collapsePattern = physicalCollapseTerms[language];
      if (collapsePattern) {
        for (const key of foldControlKeys) {
          expect(translations[key], `${language} physical collapse: ${key}`).not.toMatch(collapsePattern);
        }
        expect(translations[proxyConvergenceKey], `${language} proxy convergence`).not.toMatch(collapsePattern);
      }
      const fermentationPattern = fermentationTerms[language];
      if (fermentationPattern) {
        for (const key of developmentKeys) {
          expect(translations[key], `${language} fermentation mistranslation: ${key}`).not.toMatch(
            fermentationPattern,
          );
        }
      }
      const quotePattern = nonMarketQuoteTerms[language];
      for (const key of marketQuoteKeys) {
        expect(translations[key], `${language} market-quote concept: ${key}`).toMatch(marketQuoteMarkers[language]);
        if (quotePattern) {
          expect(translations[key], `${language} non-market quote: ${key}`).not.toMatch(quotePattern);
        }
      }
      const stalePattern = spoiledStaleTerms[language];
      if (stalePattern) {
        for (const key of [
          'utils.portfolioFormat.FX_REFRESH_TEXT.stale',
          'utils.portfolioFormat.FX_REFRESH_TEXT.summary',
        ] as const) {
          expect(translations[key], `${language} stale FX semantics: ${key}`).not.toMatch(stalePattern);
        }
      }
      expect(translations['i18n.uiText.UI_TEXT.runFlow.nodeDetails.recordCount']).toBe(
        expectedRecordCount[language],
      );
      for (const key of rsiKeys) {
        expect(translations[key], `${language} RSI literal: ${key}`).toContain('RSI');
      }
      for (const key of drawdownKeys) {
        expect(translations[key], `${language} drawdown concept: ${key}`).toMatch(drawdownMarkers[language]);
      }
      for (const key of [
        'locales.alerts.ALERT_PORTFOLIO_TYPE_OPTIONS.2.label',
        'locales.alerts.ALERT_TYPE_FILTER_OPTIONS.11.label',
        'locales.alerts.ALERT_TYPE_LABELS.portfolio_drawdown',
      ] as const) {
        expect(translations[key], `${language} drawdown alias: ${key}`).toBe(expectedDrawdown[language]);
      }
    }
  });

  it('keeps Japanese and Korean local-CLI and cooldown boundaries explicit', () => {
    const japanese = getLoadedUiLanguageTranslations('ja');
    const korean = getLoadedUiLanguageTranslations('ko');
    if (!japanese || !korean) throw new Error('Japanese and Korean bundles must be loaded');

    const backendKey =
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.agent.AGENT_GENERATION_BACKEND.valueNotes.2' as const;
    expectSemanticTranslation(
      japanese,
      backendKey,
      /利用(?:でき|不可)|使用(?:でき|不可)|実行でき/u,
      /(?:通常|標準|既定).{0,12}モデル|フォールバック/iu,
    );
    expectSemanticTranslation(
      korean,
      backendKey,
      /사용할 수 없|사용 불가|이용할 수 없|실행할 수 없/u,
      /(?:표준|일반|기본).{0,12}모델|전환|폴백|fallback/iu,
    );
    expect(japanese[backendKey]).toContain('CLI');
    expect(korean[backendKey]).toContain('CLI');

    const cooldownKey = 'locales.alerts.ALERT_LIST_TEXT.notCoolingDown' as const;
    expectSemanticTranslation(japanese, cooldownKey, /クールダウン.*(?:ではない|でない|期間外)/u, /冷え/u);
    expectSemanticTranslation(korean, cooldownKey, /쿨다운.*(?:아님|아니|않)/u, /식지/u);
  });

  it('keeps Japanese and Korean screening metrics in the stock-analysis domain', () => {
    const japanese = getLoadedUiLanguageTranslations('ja');
    const korean = getLoadedUiLanguageTranslations('ko');
    if (!japanese || !korean) throw new Error('Japanese and Korean bundles must be loaded');

    const localeSemantics = [
      {
        translations: japanese,
        stock: /銘柄/u,
        observing: /ウォッチ|監視|観察/u,
        candidate: /候補銘柄/u,
        code: /銘柄コード/u,
        canonicalTheme: /(?:正規化|標準化).{0,4}テーマ/u,
        amount: /億/u,
        coverage: /カバレッジ|網羅率|カバー/u,
        confidence: /信頼度/u,
        forbiddenStock: /資源/u,
        forbiddenCanonicalTheme: /正規テーマ/u,
        forbiddenAmount: /ドル|\$/u,
        forbiddenCoverage: /放送/u,
        forbiddenConfidence: /自信/u,
      },
      {
        translations: korean,
        stock: /종목/u,
        observing: /관찰|모니터링|주시/u,
        candidate: /후보 종목/u,
        code: /종목 코드/u,
        canonicalTheme: /(?:정규화|표준화).{0,4}테마/u,
        amount: /억/u,
        coverage: /커버리지|포괄률/u,
        confidence: /신뢰도/u,
        forbiddenStock: /자원/u,
        forbiddenCanonicalTheme: /정식 주제/u,
        forbiddenAmount: /달러|\$/u,
        forbiddenCoverage: /방송/u,
        forbiddenConfidence: /자신감/u,
      },
    ] as const;
    const candidateKeys = [
      'locales.screening.SCREENING_TEXT.candidateCount',
      'locales.screening.SCREENING_TEXT.noTaskResults',
      'locales.screening.SCREENING_TEXT.taskStats',
    ] as const;
    const confidenceKeys = [
      'locales.screening.SCREENING_TEXT.confidence',
      'locales.screening.SCREENING_TEXT.sectorThemeConfidence',
    ] as const;

    for (const semantics of localeSemantics) {
      expectSemanticTranslation(
        semantics.translations,
        'locales.screening.SCREENING_TEXT.activeStocksObserving',
        semantics.stock,
        semantics.forbiddenStock,
      );
      expect(semantics.translations['locales.screening.SCREENING_TEXT.activeStocksObserving'])
        .toMatch(semantics.observing);
      for (const key of candidateKeys) {
        expectSemanticTranslation(semantics.translations, key, semantics.candidate);
      }
      expectSemanticTranslation(
        semantics.translations,
        'locales.screening.SCREENING_TEXT.code',
        semantics.code,
      );
      expectSemanticTranslation(
        semantics.translations,
        'locales.screening.SCREENING_TEXT.canonicalTopic',
        semantics.canonicalTheme,
        semantics.forbiddenCanonicalTheme,
      );
      expectSemanticTranslation(
        semantics.translations,
        'locales.screening.SCREENING_TEXT.amountHundredMillion',
        semantics.amount,
        semantics.forbiddenAmount,
      );
      expectSemanticTranslation(
        semantics.translations,
        'locales.screening.SCREENING_TEXT.coverage',
        semantics.coverage,
        semantics.forbiddenCoverage,
      );
      expectSemanticTranslation(
        semantics.translations,
        'locales.screening.SCREENING_TEXT.stockCoverage',
        semantics.stock,
        semantics.forbiddenCoverage,
      );
      for (const key of confidenceKeys) {
        expectSemanticTranslation(
          semantics.translations,
          key,
          semantics.confidence,
          semantics.forbiddenConfidence,
        );
      }
    }
  });

  it('keeps Japanese and Korean screening lifecycle and degradation copy operational', () => {
    const japanese = getLoadedUiLanguageTranslations('ja');
    const korean = getLoadedUiLanguageTranslations('ko');
    if (!japanese || !korean) throw new Error('Japanese and Korean bundles must be loaded');

    const localeSemantics = [
      {
        translations: japanese,
        development: /発展.{0,4}タイムライン/u,
        forbiddenDevelopment: /発酵/u,
        heat: /注目度|テーマ熱度/u,
        forbiddenHeat: /発熱|加熱/u,
        enrichment: /エンリッチメント|補強|拡充/u,
        forbiddenEnrichment: /豊か|濃縮/u,
        degraded: /縮退|低下|劣化/u,
        forbiddenDegraded: /退化/u,
        unavailable: /ありません|利用不可|使えない|使用できない/u,
        noValue: /なし|ありません|返されていません|返されません|未返却/u,
        forbiddenNoValue: /判決/u,
        detailBoundary: /(?=.*理由)(?=.*(?:展開|開く))/u,
      },
      {
        translations: korean,
        development: /발전.{0,4}(?:타임라인|과정)/u,
        forbiddenDevelopment: /발효/u,
        heat: /주목도|관심도|인기도/u,
        forbiddenHeat: /열기|히트/u,
        enrichment: /보강|강화|보완/u,
        forbiddenEnrichment: /풍요|농축/u,
        degraded: /성능 저하|기능 저하|제한|저하/u,
        forbiddenDegraded: /퇴화|손상/u,
        unavailable: /없|사용 불가/u,
        noValue: /없|반환되지 않/u,
        forbiddenNoValue: /판결/u,
        detailBoundary: /(?=.*(?:이유|원인))(?=.*(?:펼쳐|확장))/u,
      },
    ] as const;
    const developmentKeys = [
      'locales.screening.SCREENING_TEXT.cachedHotspots',
      'locales.screening.SCREENING_TEXT.routeTimeline',
    ] as const;
    const heatKeys = [
      'locales.screening.SCREENING_TEXT.heat',
      'locales.screening.SCREENING_TEXT.refreshDescription',
      'locales.screening.SCREENING_TEXT.hotspotsDescription',
    ] as const;
    const enrichmentKeys = [
      'locales.screening.SCREENING_TEXT.dsaEnrichment',
      'locales.screening.SCREENING_TEXT.dsaHints',
      'locales.screening.SCREENING_TEXT.dsaSummary',
    ] as const;
    const degradedKeys = [
      'locales.screening.SCREENING_TEXT.degradedNoValue',
      'locales.screening.SCREENING_TEXT.degradedDetail',
      'locales.screening.SCREENING_TEXT.llmDegraded',
    ] as const;
    const noLlmValueKeys = [
      'locales.screening.SCREENING_TEXT.noLlmJudgement',
      'locales.screening.SCREENING_TEXT.noLlmMetadata',
    ] as const;

    for (const semantics of localeSemantics) {
      for (const key of developmentKeys) {
        expectSemanticTranslation(
          semantics.translations,
          key,
          semantics.development,
          semantics.forbiddenDevelopment,
        );
      }
      for (const key of heatKeys) {
        expectSemanticTranslation(semantics.translations, key, semantics.heat, semantics.forbiddenHeat);
      }
      for (const key of enrichmentKeys) {
        expectSemanticTranslation(
          semantics.translations,
          key,
          semantics.enrichment,
          semantics.forbiddenEnrichment,
        );
      }
      for (const key of degradedKeys) {
        expectSemanticTranslation(
          semantics.translations,
          key,
          semantics.degraded,
          semantics.forbiddenDegraded,
        );
      }
      expect(semantics.translations['locales.screening.SCREENING_TEXT.degradedDetail'])
        .toMatch(semantics.detailBoundary);
      expectSemanticTranslation(
        semantics.translations,
        'locales.screening.SCREENING_TEXT.diagnosticMissingKey',
        semantics.unavailable,
      );
      for (const key of noLlmValueKeys) {
        expectSemanticTranslation(
          semantics.translations,
          key,
          semantics.noValue,
          semantics.forbiddenNoValue,
        );
      }
    }
  });

  it('keeps Japanese and Korean screening task, reranking, and action labels distinct', () => {
    const japanese = getLoadedUiLanguageTranslations('ja');
    const korean = getLoadedUiLanguageTranslations('ko');
    if (!japanese || !korean) throw new Error('Japanese and Korean bundles must be loaded');

    const localeSemantics = [
      {
        translations: japanese,
        execution: /実行/u,
        screening: /スクリーニング/u,
        task: /タスク/u,
        waiting: /実行待ち/u,
        submission: /送信/u,
        failed: /失敗|できません/u,
        unknown: /不明/u,
        polling: /ポーリング/u,
        retry: /再試行/u,
        rerank: /再(?:ランキング|ランク付け)/u,
        notReranked: /未|されていません|なし/u,
        forbiddenWorkflow: /株式選択|ランタイム/u,
        forbiddenRerank: /ランク変更/u,
        firm: /堅調/u,
        leading: /先行|先導|主導/u,
        strong: /強い|強力/u,
        forbiddenStrength: /会社|リーディング|ストロング/u,
        watch: /注視|監視|注目/u,
        item: /項目/u,
        forbiddenWatch: /時計/u,
        custom: 'カスタム',
      },
      {
        translations: korean,
        execution: /실행/u,
        screening: /스크리닝/u,
        task: /작업/u,
        waiting: /실행 대기/u,
        submission: /제출/u,
        failed: /실패|제출할 수 없|제출하지 못/u,
        unknown: /알 수 없는/u,
        polling: /폴링/u,
        retry: /재시도|다시 시도/u,
        rerank: /재(?:랭킹|순위 조정|순위화|정렬)/u,
        notReranked: /않|아님|미실행/u,
        forbiddenWorkflow: /주식 선택|런타임|과제|출마|조사|재테스트/u,
        forbiddenRerank: /재분류|재평가/u,
        firm: /견조/u,
        leading: /선도/u,
        strong: /강함|강세|강력/u,
        forbiddenStrength: /회사|리더십|강해/u,
        watch: /관찰|주시/u,
        item: /항목/u,
        forbiddenWatch: /시계/u,
        custom: '사용자 지정',
      },
    ] as const;
    const workflowKeys = [
      'locales.screening.SCREENING_TEXT.run',
      'locales.screening.SCREENING_TEXT.runId',
      'locales.screening.SCREENING_TEXT.running',
      'locales.screening.SCREENING_TEXT.waitingRun',
      'locales.screening.SCREENING_TEXT.submittingTask',
      'locales.screening.SCREENING_TEXT.task',
      'locales.screening.SCREENING_TEXT.unknownTaskStatus',
      'locales.screening.SCREENING_TEXT.pollingTimeout',
      'locales.screening.SCREENING_TEXT.taskSubmitFailed',
    ] as const;

    for (const semantics of localeSemantics) {
      for (const key of workflowKeys) {
        const required = key === 'locales.screening.SCREENING_TEXT.runId'
          || key === 'locales.screening.SCREENING_TEXT.waitingRun'
          ? semantics.execution
          : key === 'locales.screening.SCREENING_TEXT.run'
            || key === 'locales.screening.SCREENING_TEXT.running'
            || key === 'locales.screening.SCREENING_TEXT.submittingTask'
            ? semantics.screening
            : semantics.task;
        expectSemanticTranslation(
          semantics.translations,
          key,
          required,
          semantics.forbiddenWorkflow,
        );
      }
      expect(semantics.translations['locales.screening.SCREENING_TEXT.run']).toMatch(semantics.execution);
      expect(semantics.translations['locales.screening.SCREENING_TEXT.runId']).toMatch(semantics.execution);
      expect(semantics.translations['locales.screening.SCREENING_TEXT.running']).toMatch(semantics.execution);
      expect(semantics.translations['locales.screening.SCREENING_TEXT.waitingRun']).toMatch(semantics.waiting);
      expect(semantics.translations['locales.screening.SCREENING_TEXT.submittingTask']).toMatch(semantics.task);
      expect(semantics.translations['locales.screening.SCREENING_TEXT.submittingTask']).toMatch(
        semantics.submission,
      );
      expect(semantics.translations['locales.screening.SCREENING_TEXT.unknownTaskStatus']).toMatch(
        semantics.unknown,
      );
      expect(semantics.translations['locales.screening.SCREENING_TEXT.pollingTimeout']).toMatch(semantics.task);
      expect(semantics.translations['locales.screening.SCREENING_TEXT.pollingTimeout']).toMatch(
        semantics.polling,
      );
      expect(semantics.translations['locales.screening.SCREENING_TEXT.pollingTimeout']).toMatch(semantics.retry);
      expect(semantics.translations['locales.screening.SCREENING_TEXT.taskSubmitFailed']).toMatch(
        semantics.submission,
      );
      expect(semantics.translations['locales.screening.SCREENING_TEXT.taskSubmitFailed']).toMatch(
        semantics.failed,
      );

      for (const key of [
        'locales.screening.SCREENING_TEXT.reranked',
        'locales.screening.SCREENING_TEXT.notReranked',
      ] as const) {
        expectSemanticTranslation(
          semantics.translations,
          key,
          semantics.rerank,
          semantics.forbiddenRerank,
        );
      }
      expect(semantics.translations['locales.screening.SCREENING_TEXT.notReranked'])
        .toMatch(semantics.notReranked);

      expectSemanticTranslation(
        semantics.translations,
        'locales.screening.SCREENING_TEXT.strengthFirm',
        semantics.firm,
        semantics.forbiddenStrength,
      );
      expectSemanticTranslation(
        semantics.translations,
        'locales.screening.SCREENING_TEXT.strengthLeading',
        semantics.leading,
        semantics.forbiddenStrength,
      );
      expectSemanticTranslation(
        semantics.translations,
        'locales.screening.SCREENING_TEXT.strengthStrong',
        semantics.strong,
        semantics.forbiddenStrength,
      );
      expectSemanticTranslation(
        semantics.translations,
        'locales.screening.SCREENING_TEXT.watchItems',
        semantics.watch,
        semantics.forbiddenWatch,
      );
      expect(semantics.translations['locales.screening.SCREENING_TEXT.watchItems']).toMatch(semantics.item);
      expect(semantics.translations['locales.screening.SCREENING_TEXT.custom']).toBe(semantics.custom);
      expect(placeholders(semantics.translations['locales.screening.SCREENING_TEXT.custom'])).toEqual(
        placeholders(SOURCE_UI_TRANSLATIONS['locales.screening.SCREENING_TEXT.custom']),
      );
    }
  });

  it('keeps reviewed western actions, statuses, and account labels semantically distinct', () => {
    const expectedDisableAuth: Record<WesternUiLanguage, string> = {
      de: 'Authentifizierung deaktivieren',
      es: 'Desactivar la autenticación',
      ms: 'Nyahdayakan pengesahan',
      fr: 'Désactiver l’authentification',
      id: 'Nonaktifkan autentikasi',
    };
    const expectedAlertState: Record<WesternUiLanguage, { disable: string; disabled: string }> = {
      de: { disable: 'Deaktivieren', disabled: 'Deaktiviert' },
      es: { disable: 'Desactivar', disabled: 'Desactivado' },
      ms: { disable: 'Nyahdayakan', disabled: 'Dilumpuhkan' },
      fr: { disable: 'Désactiver', disabled: 'Désactivé' },
      id: { disable: 'Nonaktifkan', disabled: 'Dinonaktifkan' },
    };
    const expectedTriggered: Record<WesternUiLanguage, string> = {
      de: 'Ausgelöst',
      es: 'Activada',
      ms: 'Dicetuskan',
      fr: 'Déclenchée',
      id: 'Dipicu',
    };
    const disableMarkers: Record<WesternUiLanguage, RegExp> = {
      de: /deaktivier/iu,
      es: /desactiv/iu,
      ms: /nyahdaya/iu,
      fr: /désactiv/iu,
      id: /nonaktif/iu,
    };

    for (const language of WESTERN_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      expect(translations['i18n.uiText.UI_TEXT.settings.disableAuth']).toBe(expectedDisableAuth[language]);
      expect(translations['i18n.uiText.UI_TEXT.settings.authPasswordHintOff']).toMatch(
        disableMarkers[language],
      );
      expect(translations['locales.alerts.ALERT_LIST_TEXT.disable']).toBe(
        expectedAlertState[language].disable,
      );
      expect(translations['locales.alerts.ALERT_LIST_TEXT.disabled']).toBe(
        expectedAlertState[language].disabled,
      );
      expect(translations['locales.alerts.ALERT_PAGE_TEXT.triggered']).toBe(expectedTriggered[language]);
    }

    const reviewedAlertLabels = {
      es: { allAccounts: 'Todas las cuentas', rule: 'Regla', skipped: /Omitidos/u },
      fr: { allAccounts: 'Tous les comptes', rule: 'Règle', skipped: /Ignorés/u },
    } as const;
    for (const language of ['es', 'fr'] as const) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      for (const key of [
        'locales.alerts.ALERT_FORM_TEXT.allAccounts',
        'locales.alerts.ALERT_LIST_TEXT.allAccounts',
        'locales.portfolio.PORTFOLIO_TEXT.allAccounts',
      ] as const) {
        expect(translations[key], `${language} all-accounts alias: ${key}`).toBe(
          reviewedAlertLabels[language].allAccounts,
        );
      }
      expect(translations['locales.alerts.ALERT_LIST_TEXT.rule']).toBe(
        reviewedAlertLabels[language].rule,
      );
      expect(translations['locales.alerts.ALERT_PAGE_TEXT.evaluationSummary']).toMatch(
        reviewedAlertLabels[language].skipped,
      );
    }
  });

  it('keeps reviewed western desktop update and smoke-check copy operational', () => {
    const checkingMarkers: Record<WesternUiLanguage, RegExp> = {
      de: /prüf|such/iu,
      es: /comprob|busc/iu,
      ms: /menyemak|memeriksa/iu,
      fr: /vérifi|recherch/iu,
      id: /memeriksa|mengecek/iu,
    };
    const versionMarkers: Record<WesternUiLanguage, RegExp> = {
      de: /Version/iu,
      es: /versi[oó]n/iu,
      ms: /versi/iu,
      fr: /version/iu,
      id: /versi/iu,
    };
    const watchlistMarkers: Record<WesternUiLanguage, RegExp> = {
      de: /Beobachtungsliste|Watchlist/iu,
      es: /lista de seguimiento/iu,
      ms: /senarai pantau/iu,
      fr: /liste de suivi/iu,
      id: /daftar pantauan/iu,
    };
    const stockMarkers: Record<WesternUiLanguage, RegExp> = {
      de: /Aktie/iu,
      es: /acci[oó]n/iu,
      ms: /saham/iu,
      fr: /action/iu,
      id: /saham/iu,
    };

    for (const language of WESTERN_UI_LANGUAGES) {
      const translations = getLoadedUiLanguageTranslations(language);
      if (!translations) throw new Error(`${language} bundle is not loaded`);
      expect(translations['i18n.uiText.UI_TEXT.settings.checkingDesktopUpdate']).toMatch(
        checkingMarkers[language],
      );
      const checkingMessage = translations['i18n.uiText.UI_TEXT.settings.desktopUpdateCheckingMessage'];
      expect(checkingMessage, `${language} desktop release source`).toContain('GitHub Releases');
      expect(checkingMessage, `${language} desktop update check`).toMatch(checkingMarkers[language]);
      expect(checkingMessage, `${language} available version`).toMatch(versionMarkers[language]);
      const smokeNeedsStock = translations['i18n.uiText.UI_TEXT.settings.setupGuideSmokeNeedsStock'];
      expect(smokeNeedsStock, `${language} smoke-check watchlist`).toMatch(watchlistMarkers[language]);
      expect(smokeNeedsStock, `${language} smoke-check stock`).toMatch(stockMarkers[language]);
    }

    const german = getLoadedUiLanguageTranslations('de');
    const french = getLoadedUiLanguageTranslations('fr');
    if (!german || !french) throw new Error('German and French bundles must be loaded');
    expect(german['i18n.uiText.UI_TEXT.settings.desktopUpdateReleaseMessage']).toContain('GitHub Releases');
    expect(german['i18n.uiText.UI_TEXT.settings.desktopUpdateReleaseMessage']).toMatch(/öffn/iu);
    expect(german['i18n.uiText.UI_TEXT.settings.desktopUpdateReleaseMessage']).toMatch(
      /herunter(?:zu)?lad/iu,
    );
    expect(german['i18n.uiText.UI_TEXT.runFlow.durationMs']).toBe('{value} ms');
    for (const key of [
      'i18n.uiText.UI_TEXT.settings.desktopDownload',
      'i18n.uiText.UI_TEXT.settings.desktopManualUnsupported',
    ] as const) {
      expect(french[key], `French release-page action: ${key}`).toMatch(/publication|version publiée/iu);
      expect(french[key], `French exit-page mistranslation: ${key}`).not.toMatch(/sortie/iu);
    }
  });

  it('keeps reviewed western settings help in the configuration and finance domains', () => {
    const german = getLoadedUiLanguageTranslations('de');
    const spanish = getLoadedUiLanguageTranslations('es');
    const malay = getLoadedUiLanguageTranslations('ms');
    const french = getLoadedUiLanguageTranslations('fr');
    const indonesian = getLoadedUiLanguageTranslations('id');
    if (!german || !spanish || !malay || !french || !indonesian) {
      throw new Error('Western locale bundles must be loaded');
    }

    const yamlEditorBoundary = german[
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.ai_model.LITELLM_CONFIG.valueNotes.1'
    ];
    expect(yamlEditorBoundary).toContain('YAML');
    expect(yamlEditorBoundary).toMatch(/nicht/iu);
    expect(malay[
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.ai_model.LLM_PROMPT_CACHE_TELEMETRY_ENABLED.summary'
    ]).toMatch(/cache gesaan/iu);

    const neutralReturnHelp = german[
      'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.backtest.eval_params.valueNotes.2'
    ];
    expect(neutralReturnHelp).toMatch(/Renditen/iu);
    expect(neutralReturnHelp).not.toMatch(/Rückgaben/iu);

    expect(german['locales.settingsWizard.SETTINGS_WIZARD_TEXT.saveFailedTitle'])
      .toBe('Speichern fehlgeschlagen');
    expect(spanish['locales.settingsWizard.SETTINGS_WIZARD_TEXT.saveFailedTitle'])
      .toBe('Error al guardar');
    const saveBoundaryMarkers = [
      { language: 'de', translations: german, negative: /nicht/iu, save: /Speichern/iu },
      { language: 'ms', translations: malay, negative: /tidak/iu, save: /simpan|penyimpan/iu },
      { language: 'id', translations: indonesian, negative: /tidak/iu, save: /simpan|penyimpan/iu },
    ] as const;
    for (const { language, translations, negative, save } of saveBoundaryMarkers) {
      const testHint = translations['locales.settingsWizard.SETTINGS_WIZARD_TEXT.testHint'];
      expect(testHint, `${language} optional test does not gate saving`).toMatch(negative);
      expect(testHint, `${language} optional test saving boundary`).toMatch(save);
    }

    const mergeFailure = spanish['i18n.uiText.UI_TEXT.settings.intelligentImportMergeFailed'];
    expect(mergeFailure).toMatch(/(?:error|fall).*(?:guard|almacen)|(?:guard|almacen).*(?:error|fall)/iu);
    expect(mergeFailure).toMatch(/fusi[oó]n|combin/iu);
    expect(mergeFailure).not.toMatch(/partida/iu);

    expect(french['locales.screening.SCREENING_TEXT.persistence']).toMatch(/persistance/iu);
    expect(malay['locales.screening.SCREENING_TEXT.persistence']).toMatch(/ketekal|persisten/iu);
    expect(indonesian['locales.screening.SCREENING_TEXT.persistence']).toMatch(/persistensi/iu);
  });

  it('matches the generated inventory to every source language registry', async () => {
    const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
    const registryFiles = listSourceFiles(sourceRoot).filter((filename) => {
      if (filename.endsWith(`${path.sep}i18n${path.sep}createUiLanguageRecord.ts`)) return false;
      return fs.readFileSync(filename, 'utf8').includes('createUiLanguageRecord(');
    });

    for (const filename of registryFiles) {
      const relativePath = path.relative(sourceRoot, filename).split(path.sep).join('/');
      const loader = Object.entries(uiTranslationModuleLoaders).find(([modulePath]) => (
        modulePath.replaceAll('\\', '/').endsWith(`/${relativePath}`)
      ))?.[1];
      expect(loader, `missing module loader for ${relativePath}`).toBeTypeOf('function');
      if (typeof loader !== 'function') throw new Error(`missing module loader for ${relativePath}`);
      await loader();
    }

    expect([...getRegisteredUiTranslationKeys()].sort()).toEqual([...UI_TRANSLATION_KEYS].sort());
    expect(UI_TRANSLATION_KEYS.some((key) => /\.(?:value|filename|id|key|href|url|route|path)$/.test(key))).toBe(false);
  });

  it('contains no duplicate object keys in locale source files', () => {
    const localesDir = path.dirname(fileURLToPath(import.meta.url)).replace(`${path.sep}__tests__`, '');
    const failures: string[] = [];
    for (const filename of fs.readdirSync(localesDir).filter((name: string) => name.endsWith('.ts'))) {
      const sourceText = fs.readFileSync(path.join(localesDir, filename), 'utf8');
      const source = ts.createSourceFile(filename, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
      const visit = (node: ts.Node) => {
        if (ts.isObjectLiteralExpression(node)) {
          const seen = new Set<string>();
          for (const property of node.properties) {
            if (!('name' in property) || !property.name) continue;
            const name = ts.isIdentifier(property.name) || ts.isStringLiteral(property.name) || ts.isNumericLiteral(property.name)
              ? property.name.text
              : undefined;
            if (!name) continue;
            if (seen.has(name)) failures.push(`${filename}:${source.getLineAndCharacterOfPosition(property.getStart()).line + 1} duplicate ${name}`);
            seen.add(name);
          }
        }
        ts.forEachChild(node, visit);
      };
      visit(source);
    }
    expect(failures).toEqual([]);
  });

  it('keeps the stale DSA product name out of registered user-facing copy', () => {
    const failures: string[] = [];
    for (const [registryName, registry] of Object.entries(registries)) {
      for (const language of UI_LANGUAGES) {
        for (const [key, value] of flatten(registry[language])) {
          if (/\bDSA\b/.test(value)) {
            failures.push(`${registryName}.${language}.${key}: ${JSON.stringify(value)}`);
          }
        }
      }
    }

    expect(failures).toEqual([]);
  });
});
