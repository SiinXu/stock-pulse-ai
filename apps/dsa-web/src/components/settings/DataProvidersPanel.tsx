import { useMemo, useState } from 'react';
import type React from 'react';
import { Database, Search } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { UiTextKey } from '../../i18n/uiText';
import type { ConfigValidationIssue, SystemConfigItem } from '../../types/systemConfig';
import { Badge, Modal } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { SettingsField } from './SettingsField';
import { DATA_PROVIDERS, getDataProviderFieldOrder } from './dataProviders';

interface DataProvidersPanelProps {
  items: SystemConfigItem[];
  disabled: boolean;
  onChange: (key: string, value: string) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  // Configured badges normally derive from field values; providers whose
  // status fields are managed outside the panel (AlphaSift) override here.
  configuredOverrides?: Record<string, boolean>;
}

const SECTION_ORDER: Array<{ group: 'quote' | 'search'; titleKey: UiTextKey; icon: LucideIcon }> = [
  { group: 'quote', titleKey: 'settings.dataGroupQuote', icon: Database },
  { group: 'search', titleKey: 'settings.dataGroupSearch', icon: Search },
];

function isProviderConfigured(items: SystemConfigItem[]): boolean {
  return items.some((item) => {
    const value = String(item.value ?? '').trim().toLowerCase();
    return value !== '' && value !== 'false';
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

  const openProvider = DATA_PROVIDERS.find((provider) => provider.id === openProviderId) ?? null;
  const openProviderItems = openProviderId ? itemsByProvider.get(openProviderId) ?? [] : [];

  return (
    <>
      <div className="space-y-4">
        {SECTION_ORDER.map((section) => {
          const providers = DATA_PROVIDERS.filter(
            (provider) => provider.group === section.group && (itemsByProvider.get(provider.id)?.length ?? 0) > 0,
          );
          if (!providers.length) {
            return null;
          }
          const SectionIcon = section.icon;
          return (
            <div key={section.group} className="space-y-2">
              <h3 className="px-1 text-sm font-medium text-secondary-text">{t(section.titleKey)}</h3>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {providers.map((provider) => {
                  const providerItems = itemsByProvider.get(provider.id) ?? [];
                  const configured =
                    configuredOverrides?.[provider.id] ??
                    isProviderConfigured(
                      providerItems.filter((item) => provider.configuredKeys.includes(item.key)),
                    );
                  return (
                    <button
                      key={provider.id}
                      type="button"
                      onClick={() => setOpenProviderId(provider.id)}
                      className={cn(
                        'flex items-center justify-between gap-2 rounded-full border settings-border bg-background/35 px-3 py-3 text-left transition-colors hover:bg-[var(--settings-surface-hover)]',
                      )}
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <SectionIcon className="h-4 w-4 shrink-0 text-muted-text" aria-hidden="true" />
                        <span className="truncate text-sm font-medium text-foreground">{provider.label}</span>
                      </span>
                      <Badge variant={configured ? 'success' : 'default'} size="sm" className="shrink-0">
                        {configured ? t('settings.providerConfigured') : t('settings.providerUnconfigured')}
                      </Badge>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <Modal
        isOpen={Boolean(openProvider)}
        onClose={() => setOpenProviderId(null)}
        title={openProvider ? openProvider.label : undefined}
        className="max-w-2xl"
      >
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
    </>
  );
};
