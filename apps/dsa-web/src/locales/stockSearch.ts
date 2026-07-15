import type { UiLanguage } from '../i18n/uiText';

const zh = {
  placeholder: '输入股票代码或名称',
  marketCN: 'A股', marketHK: '港股', marketUS: '美股', marketJP: '日股', marketKR: '韩股', marketIndex: '指数', marketBSE: '北交所',
  matchExact: '精确', matchPrefix: '前缀', matchContains: '包含', matchFuzzy: '模糊',
} as const;

const en: Record<keyof typeof zh, string> = {
  placeholder: 'Enter a stock symbol or name',
  marketCN: 'China', marketHK: 'Hong Kong', marketUS: 'US', marketJP: 'Japan', marketKR: 'Korea', marketIndex: 'Index', marketBSE: 'Beijing',
  matchExact: 'Exact', matchPrefix: 'Prefix', matchContains: 'Contains', matchFuzzy: 'Fuzzy',
};

export const STOCK_SEARCH_TEXT: Record<UiLanguage, Record<keyof typeof zh, string>> = { zh, en };
