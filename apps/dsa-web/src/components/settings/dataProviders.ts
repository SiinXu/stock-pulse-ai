// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/** Product role in the Data Sources hub (issue #867). */
export type DataProviderRole = 'baseline' | 'enhancer' | 'advanced';

/** What the provider contributes (type chip on each card). */
export type DataProviderCapability =
  | 'quote'
  | 'fundamentals'
  | 'news'
  | 'search'
  | 'specialist';

export interface DataProvider {
  id: string;
  label: string;
  /** Coarse settings grouping used by filters and legacy section filters. */
  group: 'quote' | 'search';
  role: DataProviderRole;
  capability: DataProviderCapability;
  // Field keys shown in the provider's config dialog, in display order.
  keys: string[];
  // Keys that decide the configured badge (credentials / endpoints only, so
  // fields with non-empty defaults don't make every provider look configured).
  configuredKeys: string[];
  /**
   * Built-in keyless defaults: always listed, no config dialog, health is
   * "unknown" until a runtime health API exists (do not invent live status).
   */
  statusOnly?: boolean;
}

/** Stable DOM id for deep links into a provider card (hash or scroll target). */
export function dataProviderAnchorId(providerId: string): string {
  return `data-provider-${providerId}`;
}

// Provider-specific fields merged into the single "data providers" tab; the
// remaining data_source keys (general toggles + news) stay on the source tab.
//
// Role mapping aligns with backend optional-enhancer semantics
// (actions_config_check.OPTIONAL_DATA_SOURCE_KEYS) and #867:
// - baseline: keyless built-in paths that keep the free stack working
// - enhancer: optional credentials; failure must not hard-fail the main chain
// - advanced: specialist / local endpoints that can alter reliability if mis-set
export const DATA_PROVIDERS: DataProvider[] = [
  {
    id: 'akshare',
    label: 'AkShare',
    group: 'quote',
    role: 'baseline',
    capability: 'quote',
    keys: [],
    configuredKeys: [],
    statusOnly: true,
  },
  {
    id: 'yfinance',
    label: 'yfinance',
    group: 'quote',
    role: 'baseline',
    capability: 'quote',
    keys: [],
    configuredKeys: [],
    statusOnly: true,
  },
  {
    id: 'tushare',
    label: 'Tushare',
    group: 'quote',
    role: 'enhancer',
    capability: 'fundamentals',
    keys: ['TUSHARE_TOKEN'],
    configuredKeys: ['TUSHARE_TOKEN'],
  },
  {
    id: 'tickflow',
    label: 'TickFlow',
    group: 'quote',
    role: 'enhancer',
    capability: 'quote',
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
    role: 'advanced',
    capability: 'specialist',
    keys: ['ALPHASIFT_ENABLED', 'ALPHASIFT_INSTALL_SPEC'],
    configuredKeys: ['ALPHASIFT_ENABLED'],
  },
  {
    id: 'pytdx',
    label: 'Pytdx',
    group: 'quote',
    role: 'advanced',
    capability: 'quote',
    keys: ['PYTDX_HOST', 'PYTDX_PORT', 'PYTDX_SERVERS'],
    configuredKeys: ['PYTDX_HOST', 'PYTDX_SERVERS'],
  },
  {
    id: 'futu',
    label: 'Futu OpenD',
    group: 'quote',
    role: 'advanced',
    capability: 'quote',
    keys: ['FUTU_OPEND_HOST', 'FUTU_OPEND_PORT', 'FUTU_ACC_ID', 'FUTU_SECURITY_FIRM'],
    configuredKeys: ['FUTU_OPEND_HOST', 'FUTU_ACC_ID'],
  },
  {
    id: 'tavily',
    label: 'Tavily',
    group: 'search',
    role: 'enhancer',
    capability: 'search',
    keys: ['TAVILY_API_KEYS'],
    configuredKeys: ['TAVILY_API_KEYS'],
  },
  {
    id: 'serpapi',
    label: 'SerpAPI',
    group: 'search',
    role: 'enhancer',
    capability: 'search',
    keys: ['SERPAPI_API_KEYS'],
    configuredKeys: ['SERPAPI_API_KEYS'],
  },
  {
    id: 'brave',
    label: 'Brave',
    group: 'search',
    role: 'enhancer',
    capability: 'search',
    keys: ['BRAVE_API_KEYS'],
    configuredKeys: ['BRAVE_API_KEYS'],
  },
  {
    id: 'bocha',
    label: 'Bocha',
    group: 'search',
    role: 'enhancer',
    capability: 'search',
    keys: ['BOCHA_API_KEYS'],
    configuredKeys: ['BOCHA_API_KEYS'],
  },
  {
    id: 'searxng',
    label: 'SearXNG',
    group: 'search',
    role: 'enhancer',
    capability: 'search',
    keys: ['SEARXNG_BASE_URLS', 'SEARXNG_PUBLIC_INSTANCES_ENABLED'],
    configuredKeys: ['SEARXNG_BASE_URLS', 'SEARXNG_PUBLIC_INSTANCES_ENABLED'],
  },
  {
    id: 'anspire',
    label: 'Anspire',
    group: 'search',
    role: 'enhancer',
    capability: 'search',
    keys: ['ANSPIRE_API_KEYS'],
    configuredKeys: ['ANSPIRE_API_KEYS'],
  },
  {
    id: 'minimax',
    label: 'MiniMax',
    group: 'search',
    role: 'enhancer',
    capability: 'search',
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

/** Config-derived hub status — never invents live runtime health. */
export type DataProviderHubStatus =
  | 'baseline'
  | 'configured'
  | 'unconfigured';

export function resolveDataProviderHubStatus(
  provider: DataProvider,
  configured: boolean,
): DataProviderHubStatus {
  if (provider.statusOnly || provider.role === 'baseline') {
    return 'baseline';
  }
  return configured ? 'configured' : 'unconfigured';
}
