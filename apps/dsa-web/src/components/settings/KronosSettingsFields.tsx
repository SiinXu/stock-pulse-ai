// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo } from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { ConfigValidationIssue, SystemConfigItem } from '../../types/systemConfig';
import {
  isFieldEnabledByContract,
  isFieldVisibleByContract,
  resolveFieldRequirement,
} from '../../utils/configConditions';
import { KRONOS_SETTING_KEYS } from './settingsFieldPlacement';
import { SettingsField } from './SettingsField';
import { SettingsSectionCard } from './SettingsSectionCard';

interface KronosSettingsFieldsProps {
  items: SystemConfigItem[];
  allValuesByKey: Record<string, string>;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  disabled?: boolean;
  onChange: (key: string, value: string) => void;
  readOnlyDiagnostic?: (item: SystemConfigItem) => string | null | undefined;
}

export const KronosSettingsFields: React.FC<KronosSettingsFieldsProps> = ({
  items,
  allValuesByKey,
  issueByKey,
  disabled = false,
  onChange,
  readOnlyDiagnostic,
}) => {
  const { t } = useUiLanguage();
  const kronosItems = useMemo(
    () => items
      .filter((item) => KRONOS_SETTING_KEYS.has(item.key.toUpperCase()))
      .filter((item) => isFieldVisibleByContract(item.schema?.contract, allValuesByKey))
      .sort((a, b) => (a.schema?.displayOrder ?? 0) - (b.schema?.displayOrder ?? 0)),
    [allValuesByKey, items],
  );

  if (kronosItems.length === 0) {
    return null;
  }

  return (
    <SettingsSectionCard
      title={t('settings.kronosFieldsTitle')}
      description={t('settings.kronosFieldsDescription')}
    >
      <form
        className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]"
        onSubmit={(event) => event.preventDefault()}
      >
        {kronosItems.map((item) => (
          <SettingsField
            key={item.key}
            item={item}
            value={item.value}
            disabled={disabled}
            onChange={onChange}
            issues={issueByKey[item.key] || []}
            requirement={resolveFieldRequirement(item.schema?.contract, allValuesByKey)}
            dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, allValuesByKey)}
            readOnlyDiagnostic={readOnlyDiagnostic?.(item) ?? undefined}
          />
        ))}
      </form>
    </SettingsSectionCard>
  );
};
