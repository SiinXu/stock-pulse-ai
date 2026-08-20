// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiTextKey } from '../../i18n/uiText';

export type FieldGroupDescriptor = {
  id: string;
  titleKey: UiTextKey;
};

/** Group ids that start expanded on generic Settings field lists. */
export const SETTINGS_DEFAULT_OPEN_GROUP_IDS = ['quote', 'primary', 'schedule'] as const;

export type SettingsDefaultOpenGroupId = (typeof SETTINGS_DEFAULT_OPEN_GROUP_IDS)[number];

/** Deep-link query key targeting a single Settings field (`?field=KEY`). */
export const SETTINGS_FIELD_QUERY_KEY = 'field';

const DEFAULT_OPEN_GROUP_ID_SET = new Set<string>(SETTINGS_DEFAULT_OPEN_GROUP_IDS);

export function isSettingsGroupDefaultOpen(groupId: string): boolean {
  return DEFAULT_OPEN_GROUP_ID_SET.has(groupId);
}

export function parseSettingsFieldHash(hash: string): string | null {
  if (!hash.startsWith('#setting-')) {
    return null;
  }
  const key = hash.slice('#setting-'.length).trim();
  return key.length > 0 ? key : null;
}

export function resolveSettingsRevealFieldKey(options: {
  requestKey?: string | null;
  queryField?: string | null;
  hash?: string | null;
}): string | undefined {
  const fromRequest = options.requestKey?.trim();
  if (fromRequest) {
    return fromRequest;
  }
  const fromQuery = options.queryField?.trim();
  if (fromQuery) {
    return fromQuery;
  }
  return options.hash ? parseSettingsFieldHash(options.hash) ?? undefined : undefined;
}
