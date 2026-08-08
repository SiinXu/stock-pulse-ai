// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useMemo, useState } from 'react';
import type React from 'react';
import { Database, Sparkles, Wrench } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { UiTextKey } from '../../i18n/uiText';
import type { ConfigValidationIssue, SystemConfigItem } from '../../types/systemConfig';
import { Badge, Modal, SearchInput, SelectionChip, StatusDot } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { SettingsField } from './SettingsField';
import {
  DATA_PROVIDERS,
  dataProviderAnchorId,
  resolveDataProviderHubStatus,
  type DataProvider,
  type DataProviderCapability,
  type DataProviderHubStatus,
  type DataProviderRole,
  getDataProviderFieldOrder,
} from './dataProviders';

interface DataProvidersPanelProps {
  items: SystemConfigItem[];
  disabled: boolean;
  onChange: (key: string, value: string) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  // Configured badges normally derive from field values; providers whose
  // status fields are managed outside the panel (AlphaSift) override here.
  configuredOverrides?: Record<string, boolean>;
}

type RoleFilter = 'all' | DataProviderRole;
type StatusFilter = 'all' | DataProviderHubStatus;

const ROLE_SECTION_ORDER: Array<{
  role: DataProviderRole;
  titleKey: UiTextKey;
  descriptionKey: UiTextKey;
  icon: LucideIcon;
}> = [
  {
    role: 'baseline',
    titleKey: 'settings.dataHubRoleBaseline',
    descriptionKey: 'settings.dataHubRoleBaselineHint',
    icon: Database,
  },
  {
    role: 'enhancer',
    titleKey: 'settings.dataHubRoleEnhancer',
    descriptionKey: 'settings.dataHubRoleEnhancerHint',
    icon: Sparkles,
  },
  {
    role: 'advanced',
    titleKey: 'settings.dataHubRoleAdvanced',
    descriptionKey: 'settings.dataHubRoleAdvancedHint',
    icon: Wrench,
  },
];

const CAPABILITY_LABEL_KEY: Record<DataProviderCapability, UiTextKey> = {
  quote: 'settings.dataHubCapabilityQuote',
  fundamentals: 'settings.dataHubCapabilityFundamentals',
  news: 'settings.dataHubCapabilityNews',
  search: 'settings.dataHubCapabilitySearch',
  specialist: 'settings.dataHubCapabilitySpecialist',
};

const ROLE_LABEL_KEY: Record<DataProviderRole, UiTextKey> = {
  baseline: 'settings.dataHubRoleBaseline',
  enhancer: 'settings.dataHubRoleEnhancer',
  advanced: 'settings.dataHubRoleAdvanced',
};

const STATUS_LABEL_KEY: Record<DataProviderHubStatus, UiTextKey> = {
  baseline: 'settings.dataHubStatusBaseline',
  configured: 'settings.providerConfigured',
  unconfigured: 'settings.providerUnconfigured',
};

const STATUS_DOT_TONE: Record<DataProviderHubStatus, 'success' | 'info' | 'neutral'> = {
  baseline: 'info',
  configured: 'success',
  unconfigured: 'neutral',
};

function isProviderConfigured(items: SystemConfigItem[]): boolean {
  return items.some((item) => {
    const value = String(item.value ?? '').trim().toLowerCase();
    return value !== '' && value !== 'false';
  });
}

function providerMatchesQuery(
  provider: DataProvider,
  status: DataProviderHubStatus,
  query: string,
  t: (key: UiTextKey) => string,
): boolean {
  const q = query.trim().toLowerCase();
  if (!q) {
    return true;
  }
  const haystack = [
    provider.label,
    provider.id,
    provider.role,
    provider.capability,
    provider.group,
    t(CAPABILITY_LABEL_KEY[provider.capability]),
    t(ROLE_LABEL_KEY[provider.role]),
    t(STATUS_LABEL_KEY[status]),
  ]
    .join(' ')
    .toLowerCase();
  return haystack.includes(q);
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
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

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
    return DATA_PROVIDERS.filter((provider) => {
      const providerItems = itemsByProvider.get(provider.id) ?? [];
      // Status-only baselines always appear; credential providers need at least
      // one matching config item so empty deployments do not list every search key.
      if (!provider.statusOnly && providerItems.length === 0) {
        return false;
      }
      const configured =
        configuredOverrides?.[provider.id]
        ?? isProviderConfigured(
          providerItems.filter((item) => provider.configuredKeys.includes(item.key)),
        );
      const status = resolveDataProviderHubStatus(provider, configured);
      if (roleFilter !== 'all' && provider.role !== roleFilter) {
        return false;
      }
      if (statusFilter !== 'all' && status !== statusFilter) {
        return false;
      }
      return providerMatchesQuery(provider, status, query, t);
    });
  }, [configuredOverrides, itemsByProvider, query, roleFilter, statusFilter, t]);

  const openProvider = DATA_PROVIDERS.find((provider) => provider.id === openProviderId) ?? null;
  const openProviderItems = openProviderId ? itemsByProvider.get(openProviderId) ?? [] : [];

  const roleFilterOptions: Array<{ id: RoleFilter; labelKey: UiTextKey }> = [
    { id: 'all', labelKey: 'settings.dataHubFilterAllRoles' },
    { id: 'baseline', labelKey: 'settings.dataHubRoleBaseline' },
    { id: 'enhancer', labelKey: 'settings.dataHubRoleEnhancer' },
    { id: 'advanced', labelKey: 'settings.dataHubRoleAdvanced' },
  ];
  const statusFilterOptions: Array<{ id: StatusFilter; labelKey: UiTextKey }> = [
    { id: 'all', labelKey: 'settings.dataHubFilterAllStatus' },
    { id: 'baseline', labelKey: 'settings.dataHubStatusBaseline' },
    { id: 'configured', labelKey: 'settings.providerConfigured' },
    { id: 'unconfigured', labelKey: 'settings.providerUnconfigured' },
  ];

  return (
    <>
      <div
        id="data-sources-providers"
        className="space-y-4"
        data-settings-hub="data-sources-providers"
      >
        <header className="space-y-1 px-1">
          <p className="text-xs leading-5 text-secondary-text sm:text-sm">
            {t('settings.dataHubDescription')}
          </p>
          <p className="text-xs text-muted-text">{t('settings.dataHubHealthUnknownNote')}</p>
        </header>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <SearchInput
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('settings.dataHubSearchPlaceholder')}
            aria-label={t('settings.dataHubSearchPlaceholder')}
            wrapperClassName="w-full sm:max-w-sm"
          />
        </div>

        <div className="flex flex-col gap-2" role="group" aria-label={t('settings.dataHubFiltersLabel')}>
          <div className="flex flex-wrap gap-2">
            {roleFilterOptions.map((option) => (
              <SelectionChip
                key={option.id}
                label={t(option.labelKey)}
                selected={roleFilter === option.id}
                onClick={() => setRoleFilter(option.id)}
              />
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {statusFilterOptions.map((option) => (
              <SelectionChip
                key={option.id}
                label={t(option.labelKey)}
                selected={statusFilter === option.id}
                onClick={() => setStatusFilter(option.id)}
              />
            ))}
          </div>
        </div>

        {visibleProviders.length === 0 ? (
          <p className="px-1 text-sm text-secondary-text" role="status">
            {t('settings.dataHubNoMatches')}
          </p>
        ) : (
          ROLE_SECTION_ORDER.map((section) => {
            const providers = visibleProviders.filter((provider) => provider.role === section.role);
            if (!providers.length) {
              return null;
            }
            const SectionIcon = section.icon;
            return (
              <div
                key={section.role}
                className="space-y-2"
                id={`data-sources-role-${section.role}`}
              >
                <div className="flex items-start gap-2 px-1">
                  <SectionIcon className="mt-0.5 h-4 w-4 shrink-0 text-muted-text" aria-hidden="true" />
                  <div className="min-w-0 space-y-0.5">
                    <h3 className="text-sm font-medium text-secondary-text">{t(section.titleKey)}</h3>
                    <p className="text-xs leading-5 text-muted-text">{t(section.descriptionKey)}</p>
                  </div>
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {providers.map((provider) => {
                    const providerItems = itemsByProvider.get(provider.id) ?? [];
                    const configured =
                      configuredOverrides?.[provider.id]
                      ?? isProviderConfigured(
                        providerItems.filter((item) => provider.configuredKeys.includes(item.key)),
                      );
                    const status = resolveDataProviderHubStatus(provider, configured);
                    const anchorId = dataProviderAnchorId(provider.id);
                    const cardBody = (
                      <>
                        <span className="flex min-w-0 items-start gap-2">
                          <StatusDot
                            tone={STATUS_DOT_TONE[status]}
                            className="mt-1.5"
                            aria-label={t(STATUS_LABEL_KEY[status])}
                          />
                          <span className="min-w-0 space-y-1">
                            <span className="block truncate text-sm font-medium text-foreground">
                              {provider.label}
                            </span>
                            <span className="flex flex-wrap gap-1">
                              <Badge variant="default" size="sm" className="shrink-0">
                                {t(CAPABILITY_LABEL_KEY[provider.capability])}
                              </Badge>
                              <Badge
                                variant={provider.role === 'enhancer' ? 'info' : 'default'}
                                size="sm"
                                className="shrink-0"
                              >
                                {t(ROLE_LABEL_KEY[provider.role])}
                              </Badge>
                            </span>
                            <span className="block text-xs text-muted-text">
                              {t('settings.dataHubAsOfUnavailable')}
                            </span>
                          </span>
                        </span>
                        <Badge
                          variant={
                            status === 'configured' || status === 'baseline' ? 'success' : 'default'
                          }
                          size="sm"
                          className="shrink-0"
                        >
                          {t(STATUS_LABEL_KEY[status])}
                        </Badge>
                      </>
                    );

                    if (provider.statusOnly) {
                      return (
                        <div
                          key={provider.id}
                          id={anchorId}
                          data-provider-id={provider.id}
                          data-provider-role={provider.role}
                          data-provider-status={status}
                          className={cn(
                            'flex items-start justify-between gap-2 rounded-lg border settings-border bg-background/35 px-3 py-3 text-left',
                          )}
                        >
                          {cardBody}
                        </div>
                      );
                    }

                    return (
                      <button
                        key={provider.id}
                        id={anchorId}
                        type="button"
                        data-provider-id={provider.id}
                        data-provider-role={provider.role}
                        data-provider-status={status}
                        onClick={() => setOpenProviderId(provider.id)}
                        className={cn(
                          'flex items-start justify-between gap-2 rounded-lg border settings-border bg-background/35 px-3 py-3 text-left transition-colors hover:bg-[var(--settings-surface-hover)]',
                        )}
                      >
                        {cardBody}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })
        )}
      </div>

      {openProvider && !openProvider.statusOnly ? (
        <Modal
          isOpen
          onClose={() => setOpenProviderId(null)}
          title={openProvider.label}
          size="wide"
        >
          <div className="mb-3 space-y-1 text-xs text-secondary-text">
            <p>
              {t(CAPABILITY_LABEL_KEY[openProvider.capability])}
              {' · '}
              {t(ROLE_LABEL_KEY[openProvider.role])}
            </p>
            {openProvider.role === 'enhancer' ? (
              <p>{t('settings.dataHubRoleEnhancerHint')}</p>
            ) : null}
            <p>{t('settings.dataHubHealthUnknownNote')}</p>
          </div>
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
