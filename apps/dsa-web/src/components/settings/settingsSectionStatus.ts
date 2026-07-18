// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { type SettingsSectionId } from './settingsInformationArchitecture';
import { placementForKey } from './settingsFieldPlacement';
import type { SectionStatus } from './SettingsNavigation';

interface StatusItem {
  key: string;
}

/**
 * Aggregate per-key draft/validation state into per-section status for the new
 * IA navigation. Badges convey state only (error / unsaved / needs-action),
 * never field counts, so we collapse everything to boolean flags per section.
 *
 * A key is mapped to its section via the field-level placement map, so keys
 * that share a backend category still light up distinct sections (e.g. a dirty
 * report-output key lights up "Reports" while a delivery-rule key lights up
 * "Alerts & Automation", even though both live under `notification`).
 */
export function computeSectionStatus(
  itemsByCategory: Record<string, ReadonlyArray<StatusItem>>,
  dirtyKeys: Iterable<string>,
  errorKeys: Iterable<string> = [],
): Partial<Record<SettingsSectionId, SectionStatus>> {
  const dirty = new Set(dirtyKeys);
  const errors = new Set(errorKeys);
  if (dirty.size === 0 && errors.size === 0) {
    return {};
  }

  const result: Partial<Record<SettingsSectionId, SectionStatus>> = {};
  for (const [category, items] of Object.entries(itemsByCategory)) {
    for (const item of items) {
      const isDirty = dirty.has(item.key);
      const hasError = errors.has(item.key);
      if (!isDirty && !hasError) {
        continue;
      }
      const { section } = placementForKey(category, item.key);
      const entry = result[section] ?? {};
      if (isDirty) {
        entry.isDirty = true;
      }
      if (hasError) {
        entry.hasError = true;
      }
      result[section] = entry;
    }
  }
  return result;
}
