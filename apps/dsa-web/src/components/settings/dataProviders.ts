// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
export interface DataProvider {
  id: string;
  label: string;
  group: 'quote' | 'search';
  // Field keys shown in the provider's config dialog, in display order.
  keys: string[];
  // Keys that decide the configured badge (credentials / endpoints only, so
  // fields with non-empty defaults don't make every provider look configured).
  configuredKeys: string[];
}

// Provider-specific fields merged into the single "data providers" tab; the
// remaining data_source keys (general toggles + news) stay on the source tab.
export const DATA_PROVIDERS: DataProvider[] = [
  {
    id: 'tushare',
    label: 'Tushare',
    group: 'quote',
    keys: ['TUSHARE_TOKEN'],
    configuredKeys: ['TUSHARE_TOKEN'],
  },
  {
    id: 'tickflow',
    label: 'TickFlow',
    group: 'quote',
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
    group: 'quote',
    keys: ['ALPHASIFT_ENABLED', 'ALPHASIFT_INSTALL_SPEC'],
    configuredKeys: ['ALPHASIFT_ENABLED'],
  },
  {
    id: 'pytdx',
    label: 'Pytdx',
    group: 'quote',
    keys: ['PYTDX_HOST', 'PYTDX_PORT', 'PYTDX_SERVERS'],
    configuredKeys: ['PYTDX_HOST', 'PYTDX_SERVERS'],
  },
  {
    id: 'tavily',
    label: 'Tavily',
    group: 'search',
    keys: ['TAVILY_API_KEYS'],
    configuredKeys: ['TAVILY_API_KEYS'],
  },
  {
    id: 'serpapi',
    label: 'SerpAPI',
    group: 'search',
    keys: ['SERPAPI_API_KEYS'],
    configuredKeys: ['SERPAPI_API_KEYS'],
  },
  {
    id: 'brave',
    label: 'Brave',
    group: 'search',
    keys: ['BRAVE_API_KEYS'],
    configuredKeys: ['BRAVE_API_KEYS'],
  },
  {
    id: 'bocha',
    label: 'Bocha',
    group: 'search',
    keys: ['BOCHA_API_KEYS'],
    configuredKeys: ['BOCHA_API_KEYS'],
  },
  {
    id: 'searxng',
    label: 'SearXNG',
    group: 'search',
    keys: ['SEARXNG_BASE_URLS', 'SEARXNG_PUBLIC_INSTANCES_ENABLED'],
    configuredKeys: ['SEARXNG_BASE_URLS', 'SEARXNG_PUBLIC_INSTANCES_ENABLED'],
  },
  {
    id: 'anspire',
    label: 'Anspire',
    group: 'search',
    keys: ['ANSPIRE_API_KEYS'],
    configuredKeys: ['ANSPIRE_API_KEYS'],
  },
  {
    id: 'minimax',
    label: 'MiniMax',
    group: 'search',
    keys: ['MINIMAX_API_KEYS'],
    configuredKeys: ['MINIMAX_API_KEYS'],
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
