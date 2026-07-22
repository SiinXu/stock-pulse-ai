// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export const APP_ROUTE_PATHS = {
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

export function buildSettingsSectionHref(section: string): string {
  const searchParams = new URLSearchParams({
    [SETTINGS_ROUTE_QUERY_KEYS.section]: section,
  });
  return `${APP_ROUTE_PATHS.settings}?${searchParams}`;
}
