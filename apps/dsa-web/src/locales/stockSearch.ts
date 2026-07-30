// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../i18n/uiText';

const zh = {
  inputLabel: '股票搜索',
  placeholder: '输入股票代码或名称',
  suffixExamples: '日股示例 7203.T · 韩国 KOSPI 005930.KS · KOSDAQ 035900.KQ',
  manualEntryHint: '未显示建议时，仍可输入有效的完整后缀代码并按 Enter 提交。',
  noMatchManual: '本地索引暂无匹配；有效的完整后缀代码仍可直接提交。',
  marketCN: 'A股', marketHK: '港股', marketUS: '美股', marketJP: '日股', marketKR: '韩股', marketIndex: '指数', marketBSE: '北交所',
  matchExact: '精确', matchPrefix: '前缀', matchContains: '包含', matchFuzzy: '模糊',
} as const;

const en: Record<keyof typeof zh, string> = {
  inputLabel: 'Stock search',
  placeholder: 'Enter a stock symbol or name',
  suffixExamples: 'Japan 7203.T · Korea KOSPI 005930.KS · KOSDAQ 035900.KQ',
  manualEntryHint: 'If no suggestion appears, enter a valid full suffixed symbol and press Enter.',
  noMatchManual: 'No local index match; a valid full suffixed symbol can still be submitted.',
  marketCN: 'China', marketHK: 'Hong Kong', marketUS: 'US', marketJP: 'Japan', marketKR: 'Korea', marketIndex: 'Index', marketBSE: 'Beijing',
  matchExact: 'Exact', matchPrefix: 'Prefix', matchContains: 'Contains', matchFuzzy: 'Fuzzy',
};

export const STOCK_SEARCH_TEXT: Record<UiLanguage, Record<keyof typeof zh, string>> = createUiLanguageRecord("locales.stockSearch.STOCK_SEARCH_TEXT", { zh, en });
