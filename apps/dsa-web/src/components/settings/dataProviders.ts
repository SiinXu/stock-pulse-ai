// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
export interface DataProvider {
  id: string;
  label: string;
  // Field keys shown in the provider's config dialog, in display order.
  keys: string[];
  // Keys that decide whether the directory reports an explicit stored
  // configuration. This is not a runtime-health or active-routing signal.
  configuredKeys: string[];
}

// Provider-specific market-data settings shown in the configuration directory.
// Search credentials remain on their existing Search owner and Futu OpenD stays
// outside this directory because it is owned by the portfolio-import flow.
// This list deliberately describes settings ownership only; it is not the
// runtime provider registry or an ordering/availability catalog.
export const DATA_PROVIDERS: DataProvider[] = [
  {
    id: 'tushare',
    label: 'Tushare',
    keys: ['TUSHARE_TOKEN'],
    configuredKeys: ['TUSHARE_TOKEN'],
  },
  {
    id: 'efinance',
    label: 'Efinance',
    keys: ['EFINANCE_PRIORITY', 'EFINANCE_CALL_TIMEOUT', 'ENABLE_EASTMONEY_PATCH'],
    configuredKeys: ['EFINANCE_PRIORITY', 'EFINANCE_CALL_TIMEOUT', 'ENABLE_EASTMONEY_PATCH'],
  },
  {
    id: 'akshare',
    label: 'AkShare',
    keys: ['AKSHARE_PRIORITY'],
    configuredKeys: ['AKSHARE_PRIORITY'],
  },
  {
    id: 'tickflow',
    label: 'TickFlow',
    keys: [
      'TICKFLOW_API_KEY',
      'TICKFLOW_PRIORITY',
      'TICKFLOW_KLINE_ADJUST',
      'TICKFLOW_BATCH_DAILY_ENABLED',
      'TICKFLOW_BATCH_SIZE',
    ],
    configuredKeys: ['TICKFLOW_API_KEY'],
  },
  {
    id: 'alphasift',
    label: 'AlphaSift',
    keys: [
      'ALPHASIFT_ENABLED',
      'ALPHASIFT_INSTALL_SPEC',
      'SNAPSHOT_SOURCE_PRIORITY',
      'INDUSTRY_PROVIDER',
      'INDUSTRY_PROVIDER_MAX_BOARDS',
    ],
    configuredKeys: ['ALPHASIFT_ENABLED'],
  },
  {
    id: 'pytdx',
    label: 'Pytdx',
    keys: ['PYTDX_HOST', 'PYTDX_PORT', 'PYTDX_SERVERS', 'PYTDX_PRIORITY'],
    configuredKeys: ['PYTDX_HOST', 'PYTDX_SERVERS', 'PYTDX_PRIORITY'],
  },
  {
    id: 'baostock',
    label: 'Baostock',
    keys: ['BAOSTOCK_PRIORITY'],
    configuredKeys: ['BAOSTOCK_PRIORITY'],
  },
  {
    id: 'yfinance',
    label: 'YFinance',
    keys: ['YFINANCE_PRIORITY'],
    configuredKeys: ['YFINANCE_PRIORITY'],
  },
  {
    id: 'finnhub',
    label: 'Finnhub',
    keys: ['FINNHUB_API_KEY'],
    configuredKeys: ['FINNHUB_API_KEY'],
  },
  {
    id: 'alphavantage',
    label: 'Alpha Vantage',
    keys: ['ALPHAVANTAGE_API_KEY'],
    configuredKeys: ['ALPHAVANTAGE_API_KEY'],
  },
  {
    id: 'longbridge',
    label: 'Longbridge',
    keys: [
      'LONGBRIDGE_OAUTH_CLIENT_ID',
      'LONGBRIDGE_OAUTH_TOKEN_CACHE_B64',
      'LONGBRIDGE_APP_KEY',
      'LONGBRIDGE_APP_SECRET',
      'LONGBRIDGE_ACCESS_TOKEN',
      'LONGBRIDGE_REGION',
      'LONGBRIDGE_ENABLE_OVERNIGHT',
      'LONGBRIDGE_PUSH_CANDLESTICK_MODE',
      'LONGBRIDGE_PRINT_QUOTE_PACKAGES',
      'LONGBRIDGE_PRIORITY',
    ],
    configuredKeys: [
      'LONGBRIDGE_OAUTH_CLIENT_ID',
      'LONGBRIDGE_OAUTH_TOKEN_CACHE_B64',
      'LONGBRIDGE_APP_KEY',
      'LONGBRIDGE_APP_SECRET',
      'LONGBRIDGE_ACCESS_TOKEN',
    ],
  },
  {
    id: 'social_sentiment',
    label: 'Social sentiment',
    keys: ['SOCIAL_SENTIMENT_API_KEY', 'SOCIAL_SENTIMENT_API_URL'],
    configuredKeys: ['SOCIAL_SENTIMENT_API_KEY'],
  },
];

const KEY_TO_PROVIDER = new Map<string, string>();
const KEY_ORDER = new Map<string, number>();
for (const provider of DATA_PROVIDERS) {
  for (const key of provider.keys) {
    KEY_TO_PROVIDER.set(key, provider.id);
    KEY_ORDER.set(key, KEY_ORDER.size);
  }
}

export function isDataProviderKey(key: string): boolean {
  return KEY_TO_PROVIDER.has(key);
}

export function getDataProviderFieldOrder(key: string): number {
  return KEY_ORDER.get(key) ?? Number.MAX_SAFE_INTEGER;
}
