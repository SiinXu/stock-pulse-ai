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

const STABLE_TECHNICAL_LITERAL_PATTERN = /`[^`]+`|https?:\/\/[^\s)]+|--[a-z][a-z0-9-]*|(?<![A-Za-z0-9])\.env(?:\.[a-z0-9_-]+)?\b|(?<![A-Za-z0-9_])[A-Z][A-Z0-9]*(?:_(?:<[A-Z][A-Z0-9_-]*>|[A-Z0-9]+))+(?:\([A-Z]+\))?(?![A-Za-z0-9_])|(?<![\p{L}\p{N}_.-])(?:(?:\.{1,2}\/)(?:[A-Za-z0-9._-]+\/)*[A-Za-z0-9._-]*[A-Za-z0-9_-]|\/[a-z][A-Za-z0-9._-]*\/(?:[A-Za-z0-9._-]+\/)*[A-Za-z0-9._-]*[A-Za-z0-9_-])|\b[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*_[a-z0-9_]+\b|\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b|\b(?:true|false|DEBUG|INFO|WARNING|ERROR|CRITICAL|YAML|JSON|API|CLI|LLM|HMAC|SSL|SSE|CSV|DNS|HTTP|HTTPS|TLS|ROE|FX)(?:s)?\b/gu;
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
        if (language !== 'zh-TW') {
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

  it('keeps stock and execution terminology in the financial domain', () => {
    const stockInventoryTerms: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp>> = {
      ja: /在庫/u,
      ko: /재고/u,
      de: /\b(?:Lager|Bestand|Vorrat)/iu,
      es: /\b(?:inventarios?|existencias|stocks?)\b/iu,
      ms: /\bstok\b/iu,
      fr: /\bstocks?\b/iu,
      id: /\bstok\b/iu,
    };
    const executionMistranslations: Partial<Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], RegExp>> = {
      ja: /ラン位相|運転|走行|処刑/u,
      ko: /활주로|런 토폴로지|도망|처형/u,
      de: /Lauffluss|Laufdurchfluss|Belastungslauffluss/u,
      es: /Flujo de (?:Carrera|aguas)/iu,
      ms: /\blarian\b/iu,
      fr: /Écoulement de runes|Flux de course|Débit de course/iu,
      id: /\bBerlari\b|Alur Lari/iu,
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
    }
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
