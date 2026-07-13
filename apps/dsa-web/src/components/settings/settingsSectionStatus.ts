import { legacyToSectionView, type SettingsSectionId } from './settingsInformationArchitecture';
import { getSubCategoryOfKey } from './settingsSubCategories';
import type { SectionStatus } from './SettingsNavigation';

interface StatusItem {
  key: string;
}

/**
 * Aggregate per-key draft/validation state into per-section status for the new
 * IA navigation. Badges convey state only (error / unsaved / needs-action),
 * never field counts, so we collapse everything to boolean flags per section.
 *
 * A key is mapped to its section via its backend category + sub (so, e.g., a
 * dirty notification-rule key lights up "Alerts & Automation" while a channel
 * key lights up "Notifications").
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
      const sub = getSubCategoryOfKey(category, item.key);
      const { section } = legacyToSectionView(category, sub);
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
