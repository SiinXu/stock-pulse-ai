// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useMemo, useState } from 'react';
import type React from 'react';
import { Database } from 'lucide-react';
import type { ConfigValidationIssue, SystemConfigItem } from '../../types/systemConfig';
import { Badge, Modal, SearchInput, SelectionChip } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { SettingsField } from './SettingsField';
import { DATA_PROVIDERS, getDataProviderFieldOrder } from './dataProviders';

interface DataProvidersPanelProps {
  items: SystemConfigItem[];
  disabled: boolean;
  onChange: (key: string, value: string) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  // Stored-configuration badges normally derive from explicit field values;
  // providers managed outside this panel (AlphaSift) may override them.
  configuredOverrides?: Record<string, boolean>;
}

type ConfigurationFilter = 'all' | 'configured' | 'unconfigured';

function isProviderConfigured(items: SystemConfigItem[]): boolean {
  return items.some((item) => {
    const value = String(item.value ?? '').trim().toLowerCase();
    return item.rawValueExists && value !== '' && value !== 'false';
  });
}

export const DataProvidersPanel: React.FC<DataProvidersPanelProps> = ({
  items,
  disabled,
  onChange,
  issueByKey,
  configuredOverrides,
}) => {
  const { t } = useUiLanguage();
  const [openProviderId, setOpenProviderId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [configurationFilter, setConfigurationFilter] = useState<ConfigurationFilter>('all');

  const itemsByProvider = useMemo(() => {
    const map = new Map<string, SystemConfigItem[]>();
    for (const provider of DATA_PROVIDERS) {
      map.set(
        provider.id,
        items
          .filter((item) => provider.keys.includes(item.key))
          .sort((a, b) => getDataProviderFieldOrder(a.key) - getDataProviderFieldOrder(b.key)),
      );
    }
    return map;
  }, [items]);

  const visibleProviders = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return DATA_PROVIDERS.filter((provider) => {
      const providerItems = itemsByProvider.get(provider.id) ?? [];
      if (providerItems.length === 0) {
        return false;
      }
      const configured = configuredOverrides?.[provider.id] ?? isProviderConfigured(
        providerItems.filter((item) => provider.configuredKeys.includes(item.key)),
      );
      if (configurationFilter !== 'all' && configured !== (configurationFilter === 'configured')) {
        return false;
      }
      if (!normalizedQuery) {
        return true;
      }
      const statusLabel = configured
        ? t('settings.providerConfigured')
        : t('settings.providerUnconfigured');
      return `${provider.label} ${provider.id} ${statusLabel}`.toLowerCase().includes(normalizedQuery);
    });
  }, [configurationFilter, configuredOverrides, itemsByProvider, query, t]);

  const openProvider = DATA_PROVIDERS.find((provider) => provider.id === openProviderId) ?? null;
  const openProviderItems = openProviderId ? itemsByProvider.get(openProviderId) ?? [] : [];

  return (
    <>
      <div className="space-y-4">
        <p className="px-1 text-xs leading-5 text-secondary-text sm:text-sm">
          {t('settings.dataDirectoryDescription')}
        </p>

        <h3 className="px-1 text-sm font-medium text-foreground">
          {t('settings.dataDirectoryTitle')}
        </h3>

        <SearchInput
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('settings.dataDirectorySearchPlaceholder')}
          aria-label={t('settings.dataDirectorySearchPlaceholder')}
          wrapperClassName="w-full sm:max-w-sm"
        />

        <div className="flex flex-wrap gap-2" role="group" aria-label={t('settings.dataDirectoryDescription')}>
          <SelectionChip
            label={t('settings.dataDirectoryFilterAll')}
            selected={configurationFilter === 'all'}
            onClick={() => setConfigurationFilter('all')}
          />
          <SelectionChip
            label={t('settings.providerConfigured')}
            selected={configurationFilter === 'configured'}
            onClick={() => setConfigurationFilter('configured')}
          />
          <SelectionChip
            label={t('settings.providerUnconfigured')}
            selected={configurationFilter === 'unconfigured'}
            onClick={() => setConfigurationFilter('unconfigured')}
          />
        </div>

        {visibleProviders.length === 0 ? (
          <p className="px-1 text-sm text-secondary-text" role="status">
            {t('settings.dataDirectoryNoMatches')}
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {visibleProviders.map((provider) => {
              const providerItems = itemsByProvider.get(provider.id) ?? [];
              const configured = configuredOverrides?.[provider.id] ?? isProviderConfigured(
                providerItems.filter((item) => provider.configuredKeys.includes(item.key)),
              );
              return (
                <button
                  key={provider.id}
                  type="button"
                  onClick={() => setOpenProviderId(provider.id)}
                  className={cn(
                    'flex items-center justify-between gap-2 rounded-lg border settings-border bg-background/35 px-3 py-3 text-left transition-colors hover:bg-[var(--settings-surface-hover)]',
                  )}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <Database className="h-4 w-4 shrink-0 text-muted-text" aria-hidden="true" />
                    <span className="truncate text-sm font-medium text-foreground">{provider.label}</span>
                  </span>
                  <Badge variant="default" size="sm" className="shrink-0">
                    {configured ? t('settings.providerConfigured') : t('settings.providerUnconfigured')}
                  </Badge>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {openProvider ? (
        <Modal
          isOpen
          onClose={() => setOpenProviderId(null)}
          title={openProvider.label}
          size="wide"
        >
          <p className="mb-3 text-xs leading-5 text-secondary-text">
            {t('settings.dataDirectoryDescription')}
          </p>
          <form className="divide-y divide-transparent" onSubmit={(event) => event.preventDefault()}>
            {openProviderItems.map((item) => (
              <SettingsField
                key={item.key}
                item={item}
                value={item.value}
                disabled={disabled}
                onChange={onChange}
                issues={issueByKey[item.key] || []}
              />
            ))}
          </form>
        </Modal>
      ) : null}
    </>
  );
};
