import type React from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { resolveSettingsFieldTitle } from '../../locales/settingsFieldTitle';
import type { SystemConfigItem } from '../../types/systemConfig';
import { getFieldOptionLabel } from '../../utils/systemConfigI18n';
import { getUiListSeparator } from '../../utils/uiLocale';

export interface SettingsConfigurationSummaryEntry {
  id: string;
  label: React.ReactNode;
  value: React.ReactNode;
}

export interface SettingsConfigurationSummaryProps {
  entries: readonly SettingsConfigurationSummaryEntry[];
  ariaLabel?: string;
}

export const SettingsConfigurationSummary: React.FC<SettingsConfigurationSummaryProps> = ({ entries, ariaLabel }) => (
  <dl
    aria-label={ariaLabel}
    className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-1"
  >
    {entries.map((entry) => (
      <div
        key={entry.id}
        data-testid={`settings-summary-${entry.id}`}
        className="grid min-w-0 gap-1 px-2 py-1.5 md:grid-cols-[minmax(0,1fr)_240px] md:items-center md:gap-4"
      >
        <dt className="min-w-0 text-sm text-secondary-text">{entry.label}</dt>
        <dd className="min-w-0 break-words text-sm text-foreground md:text-right">{entry.value}</dd>
      </div>
    ))}
  </dl>
);

export interface SystemConfigSummaryProps {
  items: readonly SystemConfigItem[];
  maskToken?: string;
  formatValue?: (item: SystemConfigItem, safeDefault: string) => React.ReactNode;
}

function resolveEffectiveValue(item: SystemConfigItem): string {
  const value = item.value.trim();
  if (value || item.schema?.defaultValue == null) {
    return value;
  }
  return String(item.schema.defaultValue).trim();
}

export const SystemConfigSummary: React.FC<SystemConfigSummaryProps> = ({
  items,
  maskToken = '******',
  formatValue,
}) => {
  const { language, t } = useUiLanguage();
  const entries = items.map((item) => {
    const schema = item.schema;
    const effectiveValue = resolveEffectiveValue(item);
    const optionValues = schema?.options.map((candidate) => (
      typeof candidate === 'string' ? candidate : candidate.value
    )) ?? [];
    const isBoolean = schema?.dataType === 'boolean'
      || schema?.uiControl === 'switch'
      || (
        optionValues.length === 2
        && optionValues.some((value) => value.toLowerCase() === 'true')
        && optionValues.some((value) => value.toLowerCase() === 'false')
      );
    const isProtectedValue = Boolean(
      schema?.isSensitive
      || schema?.uiControl === 'password'
      || item.isMasked
      || effectiveValue === maskToken
      || effectiveValue === '******'
      || /^(?:\*|•){3,}$/.test(effectiveValue),
    );
    const optionLabels = effectiveValue
      .split(',')
      .map((entry) => entry.trim())
      .filter(Boolean)
      .map((entry) => {
        const option = schema?.options.find((candidate) => (
          (typeof candidate === 'string' ? candidate : candidate.value) === entry
        ));
        const optionLabel = typeof option === 'string' ? undefined : option?.label;
        return option
          ? getFieldOptionLabel(schema?.key ?? item.key, entry, optionLabel, language)
          : entry;
      });
    const baseValue = !effectiveValue
      ? t('settings.providerUnconfigured')
      : isProtectedValue
        ? t('settings.providerConfigured')
      : isBoolean
        ? t(effectiveValue.toLowerCase() === 'true' ? 'common.enabled' : 'common.disabled')
        : optionLabels.join(getUiListSeparator(language));
    const safeDefault = schema?.unit && !isProtectedValue && effectiveValue
      ? `${baseValue} ${schema.unit}`
      : baseValue;
    const value = isProtectedValue ? safeDefault : (formatValue?.(item, safeDefault) ?? safeDefault);

    return {
      id: item.key,
      label: resolveSettingsFieldTitle({
        itemKey: item.key,
        schemaKey: schema?.key,
        fallbackTitle: schema?.title ?? item.key,
        language,
      }),
      value,
    };
  });

  return (
    <SettingsConfigurationSummary
      entries={entries}
      ariaLabel={t('settings.activePanelTitle')}
    />
  );
};
