// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiTextKey } from '../../i18n/uiText';
import { getCategoryFieldGroupId, getCategoryFieldOrder } from './categoryFieldGroups';
import { getNotificationFieldOrder } from './notificationFieldGroups';
import { isNotificationChannelKey } from './notificationChannels';
import { isDataProviderKey } from './dataProviders';

export interface SettingsSubCategory {
  id: string;
  titleKey: UiTextKey;
}

type ItemsByCategory = Record<string, ReadonlyArray<{ key: string }>>;

// Sub-categories that carry companion cards / dialogs and must stay visible in
// the nav even when their raw field count is zero.
export const ALWAYS_VISIBLE_SUB_CATEGORIES = new Set<string>(['channels', 'providers']);

// Coarse first-level tabs are flat (no accordion). Only data_source and
// notification are split into a couple of tabs; every other category is a
// single tab (returns null → no sub-navigation). ai_model is deliberately a
// single tab: Model Access is the only entry for provider credentials, so
// there is no separate "providers" sub.
const DATA_SOURCE_SUBS: SettingsSubCategory[] = [
  { id: 'source', titleKey: 'settings.dataTabSource' },
  { id: 'providers', titleKey: 'settings.dataTabProviders' },
];

const NOTIFICATION_SUBS: SettingsSubCategory[] = [
  { id: 'channels', titleKey: 'settings.notificationGroupChannels' },
  { id: 'rules', titleKey: 'settings.notificationTabRules' },
];

/**
 * Flat first-level tabs for a top-level settings category.
 * Returns null for categories that render as a single tab.
 */
export function getSubCategories(category: string): SettingsSubCategory[] | null {
  if (category === 'data_source') {
    return DATA_SOURCE_SUBS;
  }
  if (category === 'notification') {
    return NOTIFICATION_SUBS;
  }
  return null;
}

export function getSubCategoryOfKey(category: string, key: string): string {
  if (category === 'notification') {
    return isNotificationChannelKey(key) ? 'channels' : 'rules';
  }
  if (category === 'data_source') {
    return isDataProviderKey(key) ? 'providers' : 'source';
  }
  return getCategoryFieldGroupId(category, key);
}

export function getSubCategoryFieldOrder(category: string, key: string): number {
  if (category === 'notification') {
    return getNotificationFieldOrder(key);
  }
  return getCategoryFieldOrder(category, key);
}

export function getSubCategoryCount(
  category: string,
  subId: string,
  itemsByCategory: ItemsByCategory,
): number {
  const items = itemsByCategory[category] || [];
  return items.filter((item) => getSubCategoryOfKey(category, item.key) === subId).length;
}

/**
 * Visible flat tabs for a category: field-backed tabs with at least one item,
 * plus always-visible companion tabs (channels / providers).
 */
export function getVisibleSubCategories(
  category: string,
  itemsByCategory: ItemsByCategory,
): SettingsSubCategory[] {
  const subs = getSubCategories(category);
  if (!subs) {
    return [];
  }
  return subs.filter(
    (sub) =>
      ALWAYS_VISIBLE_SUB_CATEGORIES.has(sub.id) ||
      getSubCategoryCount(category, sub.id, itemsByCategory) > 0,
  );
}

export function getDefaultSubCategory(
  category: string,
  itemsByCategory?: ItemsByCategory,
): string | null {
  const subs = getSubCategories(category);
  if (!subs || !subs.length) {
    return null;
  }
  if (itemsByCategory) {
    const visible = getVisibleSubCategories(category, itemsByCategory);
    if (visible.length) {
      return visible[0].id;
    }
  }
  return subs[0].id;
}
