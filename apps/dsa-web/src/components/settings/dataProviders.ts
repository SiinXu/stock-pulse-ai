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
    keys: ['ALPHASIFT_ENABLED', 'ALPHASIFT_INSTALL_SPEC'],
    configuredKeys: ['ALPHASIFT_ENABLED'],
  },
  {
    id: 'pytdx',
    label: 'Pytdx',
    keys: ['PYTDX_HOST', 'PYTDX_PORT', 'PYTDX_SERVERS'],
    configuredKeys: ['PYTDX_HOST', 'PYTDX_SERVERS'],
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
