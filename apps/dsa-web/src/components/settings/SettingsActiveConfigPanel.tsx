// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { ChevronDown } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { ConfigValidationIssue, SystemConfigItem } from '../../types/systemConfig';
import {
  isFieldEnabledByContract,
  resolveFieldRequirement,
} from '../../utils/configConditions';
import { EmptyState } from '../common';
import type { UiTextKey } from '../../i18n/uiText';
// Import via the settings barrel so SettingsPage.testHarness mocks apply.
import {
  SettingsField,
  SettingsSectionCard,
  NotificationChannelsPanel,
  DataProvidersPanel,
  isNotificationChannelKey,
} from './index';
import { buildNotificationEventRoutes } from './notificationEventRoutes';

export type FieldGroupDescriptor = {
  id: string;
  titleKey: UiTextKey;
};

export type SettingsActiveConfigPanelProps = {
  panelKey: string;
  title: string;
  description: string;
  shouldRender: boolean;
  showEmptyState: boolean;
  isNotificationChannelsSub: boolean;
  isDataProvidersSub: boolean;
  visibleActiveItems: SystemConfigItem[];
  subFilteredItems: SystemConfigItem[];
  activeSubPromptCacheItems: SystemConfigItem[];
  activeFieldGroupOrder: FieldGroupDescriptor[] | null | undefined;
  fieldGroupIdOf: (key: string) => string;
  fieldGroupOrderOf: (key: string) => number;
  configuredNotificationChannels: readonly string[] | null;
  hasConfiguredNotificationChannelStatus: boolean;
  configuredRoutingValues: Set<string>;
  channelRoutingFieldKeys: Set<string>;
  channelRoutingEmptyBanner: React.ReactNode;
  channelRoutingEmptyState: React.ReactNode;
  channelRoutingOptionFilter: (optionValue: string) => boolean;
  isSaving: boolean;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  allValuesByKey: Record<string, string>;
  alphasiftEnabled: boolean;
  setDraftValue: (key: string, value: string) => void;
  readOnlyDiagnosticForItem: (item: SystemConfigItem, categoryHint?: string) => string | undefined;
  activeCategory: string;
  /** Optional mask token so notification channel cards can run test-to-bind. */
  maskToken?: string;
};

/**
 * Generic field panel for the active settings category/view
 * (notification channels, data providers, grouped fields, prompt-cache advanced).
 */
const SettingsActiveConfigPanel: React.FC<SettingsActiveConfigPanelProps> = ({
  panelKey,
  title,
  description,
  shouldRender,
  showEmptyState,
  isNotificationChannelsSub,
  isDataProvidersSub,
  visibleActiveItems,
  subFilteredItems,
  activeSubPromptCacheItems,
  activeFieldGroupOrder,
  fieldGroupIdOf,
  fieldGroupOrderOf,
  configuredNotificationChannels,
  hasConfiguredNotificationChannelStatus,
  configuredRoutingValues,
  channelRoutingFieldKeys,
  channelRoutingEmptyBanner,
  channelRoutingEmptyState,
  channelRoutingOptionFilter,
  isSaving,
  issueByKey,
  allValuesByKey,
  alphasiftEnabled,
  setDraftValue,
  readOnlyDiagnosticForItem,
  activeCategory,
  maskToken,
}) => {
  const { t } = useUiLanguage();

  if (!shouldRender) {
    if (showEmptyState) {
      return (
        <EmptyState
          title={t('settings.currentCategoryEmptyTitle')}
          description={t('settings.currentCategoryEmptyDescription')}
        />
      );
    }
    return null;
  }

  const notificationEventRoutes = isNotificationChannelsSub
    ? buildNotificationEventRoutes(allValuesByKey)
    : null;

  const content = (
    <>
      {isNotificationChannelsSub ? (
        <NotificationChannelsPanel
          items={visibleActiveItems.filter((item) => isNotificationChannelKey(item.key))}
          configuredChannels={configuredNotificationChannels}
          disabled={isSaving}
          onChange={setDraftValue}
          issueByKey={issueByKey}
          eventRoutes={notificationEventRoutes}
          maskToken={maskToken}
        />
      ) : isDataProvidersSub ? (
        <DataProvidersPanel
          items={subFilteredItems}
          disabled={isSaving}
          onChange={setDraftValue}
          issueByKey={issueByKey}
          configuredOverrides={{ alphasift: alphasiftEnabled }}
        />
      ) : activeFieldGroupOrder ? (
        <div className="space-y-4">
          {activeFieldGroupOrder.map((group) => {
            const groupItems = subFilteredItems
              .filter((item) => fieldGroupIdOf(item.key) === group.id)
              .sort((a, b) => fieldGroupOrderOf(a.key) - fieldGroupOrderOf(b.key));
            if (!groupItems.length) {
              return null;
            }
            const showChannelRoutingEmptyBanner = hasConfiguredNotificationChannelStatus
              && configuredRoutingValues.size === 0
              && groupItems.some((item) => channelRoutingFieldKeys.has(item.key));
            return (
              <div key={group.id} className="space-y-2">
                <h3 className="px-1 text-sm font-medium text-secondary-text">{t(group.titleKey)}</h3>
                {showChannelRoutingEmptyBanner ? channelRoutingEmptyBanner : null}
                <form
                  className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-1"
                  onSubmit={(event) => event.preventDefault()}
                >
                  {groupItems.map((item) => (
                    <SettingsField
                      key={item.key}
                      item={item}
                      value={item.value}
                      disabled={isSaving}
                      onChange={setDraftValue}
                      issues={issueByKey[item.key] || []}
                      requirement={resolveFieldRequirement(item.schema?.contract, allValuesByKey)}
                      dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, allValuesByKey)}
                      readOnlyDiagnostic={readOnlyDiagnosticForItem(item, activeCategory)}
                      enumOptionFilter={
                        channelRoutingFieldKeys.has(item.key) && hasConfiguredNotificationChannelStatus
                          ? channelRoutingOptionFilter
                          : undefined
                      }
                      enumEmptyState={
                        channelRoutingFieldKeys.has(item.key) && hasConfiguredNotificationChannelStatus
                          ? channelRoutingEmptyState
                          : undefined
                      }
                    />
                  ))}
                </form>
              </div>
            );
          })}
        </div>
      ) : subFilteredItems.length ? (
        <form
          className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-1"
          onSubmit={(event) => event.preventDefault()}
        >
          {subFilteredItems.map((item) => (
            <SettingsField
              key={item.key}
              item={item}
              value={item.value}
              disabled={isSaving}
              onChange={setDraftValue}
              issues={issueByKey[item.key] || []}
              requirement={resolveFieldRequirement(item.schema?.contract, allValuesByKey)}
              dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, allValuesByKey)}
              readOnlyDiagnostic={readOnlyDiagnosticForItem(item, activeCategory)}
            />
          ))}
        </form>
      ) : null}
      {activeSubPromptCacheItems.length ? (
        <details className="group/prompt-cache overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] transition-colors duration-200 hover:bg-[var(--settings-surface-hover)]">
          <summary className="flex cursor-pointer list-none items-start justify-between gap-3 px-4 py-4 [&::-webkit-details-marker]:hidden">
            <div className="min-w-0 space-y-1">
              <p className="text-sm font-semibold text-foreground">
                {t('settings.promptCacheAdvancedTitle')}
              </p>
              <p className="text-xs leading-5 text-muted-text">
                {t('settings.promptCacheAdvancedDescription')}
              </p>
            </div>
            <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-text transition-transform group-open/prompt-cache:rotate-180" aria-hidden="true" />
          </summary>
          <form
            className="border-t border-[var(--settings-border-soft)]"
            onSubmit={(event) => event.preventDefault()}
          >
            {activeSubPromptCacheItems.map((item) => (
              <SettingsField
                key={item.key}
                item={item}
                value={item.value}
                disabled={isSaving}
                onChange={setDraftValue}
                issues={issueByKey[item.key] || []}
                requirement={resolveFieldRequirement(item.schema?.contract, allValuesByKey)}
                dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, allValuesByKey)}
                readOnlyDiagnostic={readOnlyDiagnosticForItem(item, activeCategory)}
              />
            ))}
          </form>
        </details>
      ) : null}
    </>
  );

  return (
    <SettingsSectionCard
      key={panelKey}
      title={title}
      description={description}
    >
      {content}
    </SettingsSectionCard>
  );
};

export default SettingsActiveConfigPanel;
