// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export const APP_ROUTE_PATHS = {
  home: '/',
  settings: '/settings',
} as const;

export const LEGACY_ROUTE_PATHS = {
  usage: '/usage',
} as const;

export const SETTINGS_ROUTE_QUERY_KEYS = {
  section: 'section',
  view: 'view',
  legacyCategory: 'category',
  legacySub: 'sub',
  source: 'from',
} as const;

export const SETTINGS_SECTION_IDS = {
  usage: 'usage',
} as const;

export type SettingsRouteSearch = {
  section?: string;
  view?: string;
  legacyCategory?: string;
  legacySub?: string;
  source?: string;
};

export function buildSettingsHref(search: SettingsRouteSearch = {}): string {
  const searchParams = new URLSearchParams();
  const entries: Array<[keyof SettingsRouteSearch, string]> = [
    ['section', SETTINGS_ROUTE_QUERY_KEYS.section],
    ['view', SETTINGS_ROUTE_QUERY_KEYS.view],
    ['legacyCategory', SETTINGS_ROUTE_QUERY_KEYS.legacyCategory],
    ['legacySub', SETTINGS_ROUTE_QUERY_KEYS.legacySub],
    ['source', SETTINGS_ROUTE_QUERY_KEYS.source],
  ];

  entries.forEach(([field, queryKey]) => {
    const value = search[field];
    if (value) searchParams.set(queryKey, value);
  });

  const query = searchParams.toString();
  return query ? `${APP_ROUTE_PATHS.settings}?${query}` : APP_ROUTE_PATHS.settings;
}

export function buildSettingsSectionHref(section: string): string {
  return buildSettingsHref({ section });
}
