import { useMemo, useState } from 'react';
import type React from 'react';
import { Layers3 } from 'lucide-react';
import type { ConfigValidationIssue, SystemConfigItem } from '../../types/systemConfig';
import { Badge, Modal } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { SettingsField } from './SettingsField';
import { getCategoryFieldGroupId } from './categoryFieldGroups';
import { MODEL_PROVIDERS } from './modelProviders';

interface ModelProvidersPanelProps {
  items: SystemConfigItem[];
  disabled: boolean;
  onChange: (key: string, value: string) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
}

function isProviderConfigured(items: SystemConfigItem[]): boolean {
  return items.some((item) => {
    const value = String(item.value ?? '').trim().toLowerCase();
    return value !== '' && value !== 'false';
  });
}

export const ModelProvidersPanel: React.FC<ModelProvidersPanelProps> = ({
  items,
  disabled,
  onChange,
  issueByKey,
}) => {
  const { t } = useUiLanguage();
  const [openProviderId, setOpenProviderId] = useState<string | null>(null);

  const itemsByProvider = useMemo(() => {
    const map = new Map<string, SystemConfigItem[]>();
    for (const provider of MODEL_PROVIDERS) {
      map.set(provider.id, []);
    }
    for (const item of items) {
      const providerId = getCategoryFieldGroupId('ai_model', item.key);
      if (map.has(providerId)) {
        map.get(providerId)?.push(item);
      }
    }
    return map;
  }, [items]);

  const openProvider = MODEL_PROVIDERS.find((provider) => provider.id === openProviderId) ?? null;
  const openProviderItems = openProviderId ? itemsByProvider.get(openProviderId) ?? [] : [];

  return (
    <>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {MODEL_PROVIDERS.map((provider) => {
          const providerItems = itemsByProvider.get(provider.id) ?? [];
          if (providerItems.length === 0) {
            return null;
          }
          const configured = isProviderConfigured(
            providerItems.filter((item) => provider.configuredKeys.includes(item.key)),
          );
          return (
            <button
              key={provider.id}
              type="button"
              onClick={() => setOpenProviderId(provider.id)}
              className={cn(
                'flex items-center justify-between gap-2 rounded-xl border settings-border bg-background/35 px-3 py-3 text-left transition-colors hover:bg-[var(--settings-surface-hover)]',
              )}
            >
              <span className="flex min-w-0 items-center gap-2">
                <Layers3 className="h-4 w-4 shrink-0 text-muted-text" aria-hidden="true" />
                <span className="truncate text-sm font-medium text-foreground">{provider.label}</span>
              </span>
              <Badge variant={configured ? 'success' : 'default'} size="sm" className="shrink-0">
                {configured ? t('settings.providerConfigured') : t('settings.providerUnconfigured')}
              </Badge>
            </button>
          );
        })}
      </div>

      <Modal
        isOpen={Boolean(openProvider)}
        onClose={() => setOpenProviderId(null)}
        title={openProvider ? openProvider.label : undefined}
        className="max-w-2xl"
      >
        <div className="divide-y divide-transparent">
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
        </div>
      </Modal>
    </>
  );
};
