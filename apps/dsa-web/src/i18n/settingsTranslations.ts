// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { MODEL_SOURCE_LIFECYCLE_TRANSLATIONS as MODEL } from './modelSourceLifecycleTranslations';
import { MULTI_LEVEL_REFLECTION_TRANSLATIONS as REFLECTION } from './multiLevelReflectionTranslations';
import { DATA_PROVIDER_RUNTIME_TRANSLATIONS as DATA_RUNTIME } from './dataProviderRuntimeTranslations';

const SETTINGS_FIELD_TRANSLATIONS = {
  de: {
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA": "Voreinstellung der Forschungshaltung",
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA_CUSTOM": "Eigene Forschungshaltung",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_BUDGET_SECONDS": "Parallele Abfrage – Gesamtbudget (Sekunden)",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_ENABLED": "Parallele Marktdaten-Abfrage",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_MAX_CONCURRENT": "Parallele Abfrage – globales Limit",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_PER_PROVIDER_LIMIT": "Parallele Abfrage – Limit pro Provider",
  },
  es: {
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA": "Preajuste de postura de investigación",
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA_CUSTOM": "Postura de investigación personalizada",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_BUDGET_SECONDS": "Presupuesto de extracción paralela (segundos)",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_ENABLED": "Extracción paralela de datos de mercado",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_MAX_CONCURRENT": "Tope global de extracción paralela",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_PER_PROVIDER_LIMIT": "Tope por proveedor de extracción paralela",
  },
  fr: {
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA": "Préréglage de posture de recherche",
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA_CUSTOM": "Texte personnalisé de posture de recherche",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_BUDGET_SECONDS": "Budget d’extraction parallèle (secondes)",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_ENABLED": "Extraction parallèle des données de marché",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_MAX_CONCURRENT": "Plafond global d’extraction parallèle",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_PER_PROVIDER_LIMIT": "Plafond par fournisseur d’extraction parallèle",
  },
  id: {
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA": "Preset Sikap Riset",
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA_CUSTOM": "Teks Sikap Riset Khusus",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_BUDGET_SECONDS": "Anggaran tarikan paralel (detik)",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_ENABLED": "Tarikan data pasar paralel",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_MAX_CONCURRENT": "Batas global tarikan paralel",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_PER_PROVIDER_LIMIT": "Batas per-penyedia tarikan paralel",
  },
  ja: {
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA": "調査姿勢プリセット",
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA_CUSTOM": "独自の調査姿勢テキスト",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_BUDGET_SECONDS": "並行取得の総予算（秒）",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_ENABLED": "市場入力の並行取得",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_MAX_CONCURRENT": "並行取得の全体上限",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_PER_PROVIDER_LIMIT": "並行取得のプロバイダ別上限",
  },
  ko: {
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA": "연구 관점 프리셋",
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA_CUSTOM": "사용자 지정 연구 관점 텍스트",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_BUDGET_SECONDS": "병렬 수집 총 예산(초)",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_ENABLED": "시장 입력 병렬 수집",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_MAX_CONCURRENT": "병렬 수집 전역 상한",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_PER_PROVIDER_LIMIT": "병렬 수집 제공자별 상한",
  },
  ms: {
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA": "Pratetap Pendirian Penyelidikan",
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA_CUSTOM": "Teks Pendirian Penyelidikan Tersuai",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_BUDGET_SECONDS": "Bajet tarikan selari (saat)",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_ENABLED": "Tarikan data pasaran selari",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_MAX_CONCURRENT": "Had global tarikan selari",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_PER_PROVIDER_LIMIT": "Had per-pembekal tarikan selari",
  },
  "zh-TW": {
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA": "研究立場預設",
    "utils.systemConfigI18n.fieldTitleMaps.AGENT_RESEARCH_PERSONA_CUSTOM": "自訂研究立場",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_BUDGET_SECONDS": "並行取數總預算（秒）",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_ENABLED": "分析內並行取數",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_MAX_CONCURRENT": "並行取數全域並行上限",
    "utils.systemConfigI18n.fieldTitleMaps.ANALYSIS_PARALLEL_FETCH_PER_PROVIDER_LIMIT": "並行取數單源並行上限",
  },
} as const;

/** Shared settings translations kept outside the per-locale application chunks. */
export const SETTINGS_TRANSLATIONS = {
  de: { ...MODEL.de, ...REFLECTION.de, ...DATA_RUNTIME.de, ...SETTINGS_FIELD_TRANSLATIONS.de },
  es: { ...MODEL.es, ...REFLECTION.es, ...DATA_RUNTIME.es, ...SETTINGS_FIELD_TRANSLATIONS.es },
  fr: { ...MODEL.fr, ...REFLECTION.fr, ...DATA_RUNTIME.fr, ...SETTINGS_FIELD_TRANSLATIONS.fr },
  id: { ...MODEL.id, ...REFLECTION.id, ...DATA_RUNTIME.id, ...SETTINGS_FIELD_TRANSLATIONS.id },
  ja: { ...MODEL.ja, ...REFLECTION.ja, ...DATA_RUNTIME.ja, ...SETTINGS_FIELD_TRANSLATIONS.ja },
  ko: { ...MODEL.ko, ...REFLECTION.ko, ...DATA_RUNTIME.ko, ...SETTINGS_FIELD_TRANSLATIONS.ko },
  ms: { ...MODEL.ms, ...REFLECTION.ms, ...DATA_RUNTIME.ms, ...SETTINGS_FIELD_TRANSLATIONS.ms },
  "zh-TW": {
    ...MODEL["zh-TW"],
    ...REFLECTION["zh-TW"],
    ...DATA_RUNTIME["zh-TW"],
    ...SETTINGS_FIELD_TRANSLATIONS["zh-TW"],
  },
} as const;
