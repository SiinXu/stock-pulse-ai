// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Isolated per-symbol episode-forget settings-help copy (Refs #1119).
 *
 * Keep this module off SettingsPage / settings-route / locale-* /
 * extra-locale-* families, and do not emit a new entry-map filename
 * (that inflates criticalPath). Attach it to the existing CredentialInput
 * lazy chunk, same boundary as skillRetrievalSettingsHelp.ts.
 * Do not import it from settingsTranslations or core locale packs.
 */
import type { UiLanguage } from '../i18n/uiLanguages';
import type { SettingsHelpDefinition, SettingsHelpSourceMap } from './settingsHelpSourceTypes';

type AdditionalEpisodeForgetLanguage = Exclude<UiLanguage, 'zh' | 'en'>;

export const EPISODE_RETENTION_HELP_KEY = 'settings.agent.AGENT_EPISODE_RETENTION_DAYS';
export const EPISODE_MAX_ROWS_HELP_KEY = 'settings.agent.AGENT_EPISODE_MAX_ROWS';

export const EPISODE_FORGET_FIELD_DESCRIPTION = {
  AGENT_EPISODE_RETENTION_DAYS:
    '按标的 episode 最大保留天数；仅在该标的追加成功后清理。无标的不删除，不是全表清理。',
  AGENT_EPISODE_MAX_ROWS:
    '按标的 episode 行数上限；仅删除同一标的最旧行。50000 不是全表上限。',
} as const;

const episodeForgetSettingsHelpEn: Record<'retention' | 'maxRows', SettingsHelpDefinition> = {
  retention: {
    summary:
      'Per-symbol maximum episode age after that symbol is appended. Missing symbol skips delete; this is not a table-wide purge.',
  },
  maxRows: {
    summary:
      'Per-symbol episode row cap after that symbol is appended; oldest same-symbol rows drop first. 50000 is not a table ceiling. Missing symbol skips delete.',
  },
};

const episodeForgetSettingsHelpZh: Record<'retention' | 'maxRows', SettingsHelpDefinition> = {
  retention: {
    summary:
      '按标的 episode 最大保留天数；仅在该标的追加成功后删除更早的行。无标的不删除，不是全表清理。',
  },
  maxRows: {
    summary:
      '按标的 episode 行数上限；仅删除同一标的最旧行。50000 不是全表上限。无标的不删除。',
  },
};

// Single-quoted help keys so TestSettingsHelpContract can discover them.
export const EPISODE_FORGET_SETTINGS_HELP_EN: SettingsHelpSourceMap = {
  'settings.agent.AGENT_EPISODE_RETENTION_DAYS': {
    ...episodeForgetSettingsHelpEn.retention,
  },
  'settings.agent.AGENT_EPISODE_MAX_ROWS': {
    ...episodeForgetSettingsHelpEn.maxRows,
  },
};

export const EPISODE_FORGET_SETTINGS_HELP_ZH: SettingsHelpSourceMap = {
  'settings.agent.AGENT_EPISODE_RETENTION_DAYS': {
    ...episodeForgetSettingsHelpZh.retention,
  },
  'settings.agent.AGENT_EPISODE_MAX_ROWS': {
    ...episodeForgetSettingsHelpZh.maxRows,
  },
};

type ExtraEpisodeForgetHelp = {
  retention: string;
  maxRows: string;
};

const EXTRA_EPISODE_FORGET_HELP = {
  de: {
    retention:
      'Maximales Episodenalter je Symbol nach einem Append für dieses Symbol. Ohne Symbol keine Löschung; keine tabellenweite Bereinigung.',
    maxRows:
      'Zeilenobergrenze je Symbol nach einem Append; älteste Zeilen desselben Symbols zuerst. 50000 ist keine Tabellenobergrenze. Ohne Symbol keine Löschung.',
  },
  es: {
    retention:
      'Edad máxima por símbolo después de un append de ese símbolo. Sin símbolo no se borra; no es una limpieza de toda la tabla.',
    maxRows:
      'Tope de filas por símbolo tras un append; se eliminan primero las filas más antiguas del mismo símbolo. 50000 no es un techo de tabla. Sin símbolo no se borra.',
  },
  fr: {
    retention:
      'Âge maximal par symbole après un ajout pour ce symbole. Sans symbole, aucune suppression ; ce n\'est pas une purge de toute la table.',
    maxRows:
      'Plafond de lignes par symbole après un ajout ; les plus anciennes du même symbole d\'abord. 50000 n\'est pas un plafond de table. Sans symbole, aucune suppression.',
  },
  id: {
    retention:
      'Usia maksimum episode per simbol setelah append simbol itu. Tanpa simbol, tidak ada penghapusan; ini bukan pembersihan seluruh tabel.',
    maxRows:
      'Batas baris per simbol setelah append; baris tertua simbol yang sama dihapus lebih dulu. 50000 bukan plafon tabel. Tanpa simbol, tidak ada penghapusan.',
  },
  ja: {
    retention:
      '銘柄ごとのエピソード保持日数です。その銘柄の追加後に、より古い行だけを削除します。銘柄が無い場合は削除しません。テーブル全体の掃除ではありません。',
    maxRows:
      '銘柄ごとの行数上限です。その銘柄の追加後に、同じ銘柄の古い行から削除します。50000 はテーブル全体の上限ではありません。銘柄が無い場合は削除しません。',
  },
  ko: {
    retention:
      '종목별 에피소드 최대 보존 일수입니다. 해당 종목이 추가된 뒤에만 더 오래된 행을 삭제합니다. 종목이 없으면 삭제하지 않으며 테이블 전체 정리가 아닙니다.',
    maxRows:
      '종목별 에피소드 행 수 상한입니다. 해당 종목이 추가된 뒤에만 같은 종목의 가장 오래된 행부터 삭제합니다. 50000은 테이블 전체 상한이 아닙니다. 종목이 없으면 삭제하지 않습니다.',
  },
  ms: {
    retention:
      'Umur maksimum episod setiap simbol selepas append simbol itu. Tanpa simbol tiada pemadaman; ini bukan pembersihan seluruh jadual.',
    maxRows:
      'Had baris setiap simbol selepas append; baris tertua simbol yang sama dibuang dahulu. 50000 bukan siling jadual. Tanpa simbol tiada pemadaman.',
  },
  "zh-TW": {
    retention:
      '依標的 episode 最大保留天數；僅在該標的成功追加後刪除更早的列。無標的不刪除，不是整張表清理。',
    maxRows:
      '依標的 episode 列數上限；該標的成功追加後只刪除同一標的最舊列。50000 不是全表上限。無標的不刪除。',
  },
} as const satisfies Record<AdditionalEpisodeForgetLanguage, ExtraEpisodeForgetHelp>;

export function isEpisodeForgetHelpKey(helpKey: string): boolean {
  return (
    helpKey === EPISODE_RETENTION_HELP_KEY
    || helpKey === EPISODE_MAX_ROWS_HELP_KEY
    || helpKey === 'AGENT_EPISODE_RETENTION_DAYS'
    || helpKey === 'AGENT_EPISODE_MAX_ROWS'
  );
}

export function getEpisodeForgetSettingsHelp(language: UiLanguage, helpKey: string): SettingsHelpDefinition {
  const field = helpKey.endsWith('AGENT_EPISODE_MAX_ROWS') ? 'maxRows' : 'retention';
  if (language === 'zh') {
    return episodeForgetSettingsHelpZh[field];
  }
  if (language === 'en') {
    return episodeForgetSettingsHelpEn[field];
  }
  return { summary: EXTRA_EPISODE_FORGET_HELP[language][field] };
}

