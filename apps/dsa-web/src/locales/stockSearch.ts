// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../i18n/uiText';

const zh = {
  inputLabel: '股票搜索',
  placeholder: '输入股票代码或名称',
  marketCN: 'A股', marketHK: '港股', marketUS: '美股', marketJP: '日股', marketKR: '韩股', marketIndex: '指数', marketBSE: '北交所',
  matchExact: '精确', matchPrefix: '前缀', matchContains: '包含', matchFuzzy: '模糊',
} as const;

const en: Record<keyof typeof zh, string> = {
  inputLabel: 'Stock search',
  placeholder: 'Enter a stock symbol or name',
  marketCN: 'China', marketHK: 'Hong Kong', marketUS: 'US', marketJP: 'Japan', marketKR: 'Korea', marketIndex: 'Index', marketBSE: 'Beijing',
  matchExact: 'Exact', matchPrefix: 'Prefix', matchContains: 'Contains', matchFuzzy: 'Fuzzy',
};

export const STOCK_SEARCH_TEXT: Record<UiLanguage, Record<keyof typeof zh, string>> = createUiLanguageRecord("locales.stockSearch.STOCK_SEARCH_TEXT", { zh, en });
