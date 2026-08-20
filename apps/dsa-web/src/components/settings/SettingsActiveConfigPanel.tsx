// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { lazy, Suspense } from 'react';
import type React from 'react';
import { ChevronDown } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { ConfigValidationIssue, SystemConfigItem } from '../../types/systemConfig';
import {
  isFieldEnabledByContract,
  resolveFieldRequirement,
} from '../../utils/configConditions';
import { EmptyState } from '../common';
import type { FieldGroupDescriptor } from './settingsFieldGroupDisclosure';
// Import via the settings barrel so SettingsPage.testHarness mocks apply.
import {
  SettingsField,
  SettingsSectionCard,
  NotificationChannelsPanel,
  DataProvidersPanel,
  isNotificationChannelKey,
} from './index';
import {
  buildNotificationEventBindingUpdates,
  buildNotificationEventRoutes,
  NOTIFICATION_EVENT_ROUTE_KEYS,
} from './notificationEventRoutes';
import { AgentBehaviorPanel } from './AgentBehaviorPanel';
import type { AgentModelSummary } from './AgentBehaviorPanel';
import type { SettingsSaveStatus } from './autosaveMachine';

export type { FieldGroupDescriptor };

const SettingsFieldGroupPanel = lazy(() => import('./SettingsFieldGroupPanel'));

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
  persistedValuesByKey: Record<string, string>;
  alphasiftEnabled: boolean;
  setDraftValue: (key: string, value: string) => void;
  applyPartialUpdate: (items: Array<{ key: string; value: string }>) => void;
  resetDraftKeys: (keys: string[]) => void;
  activeSaveStatus: SettingsSaveStatus;
  agentModelSummary: AgentModelSummary;
  /** When true, Agent Behavior opens essentials-first (chat/remediation deep links). */
  agentEssentialsFocus?: boolean;
  readOnlyDiagnosticForItem: (item: SystemConfigItem, categoryHint?: string) => string | undefined;
  activeCategory: string;
  /** Optional mask token so notification channel cards can run test-to-bind. */
  maskToken?: string;
  configVersion: string;
  /** Search, deep-link, or error-jump target that must reveal its collapsed group. */
  revealFieldKey?: string | null;
  /** Bumped on each jump so the same field can re-open a user-collapsed group. */
  revealRequestId?: number | null;
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
  persistedValuesByKey,
  alphasiftEnabled,
  setDraftValue,
  applyPartialUpdate,
  resetDraftKeys,
  activeSaveStatus,
  agentModelSummary,
  agentEssentialsFocus = false,
  readOnlyDiagnosticForItem,
  activeCategory,
  maskToken,
  configVersion,
  revealFieldKey = null,
  revealRequestId = null,
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
    ? buildNotificationEventRoutes(persistedValuesByKey, configuredNotificationChannels)
    : null;
  const draftNotificationEventRoutes = isNotificationChannelsSub
    ? buildNotificationEventRoutes(allValuesByKey, configuredNotificationChannels)
    : null;
  const hasPendingNotificationRoutes = isNotificationChannelsSub
    && NOTIFICATION_EVENT_ROUTE_KEYS.some(
      (key) => String(allValuesByKey[key] ?? '') !== String(persistedValuesByKey[key] ?? ''),
    );

  // Agent Behavior (execution) gets preset-first progressive disclosure.
  // Conversation still maps to category `agent` but only context keys —
  // keep the generic grouped renderer there so compression fields stay flat.
  const isAgentBehaviorPanel = activeCategory === 'agent'
    && subFilteredItems.some((item) => {
      const upper = item.key.toUpperCase();
      return !upper.startsWith('AGENT_CONTEXT_') && !upper.startsWith('AGENT_EVENT_');
    });

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
          draftEventRoutes={draftNotificationEventRoutes}
          hasPendingRoutes={hasPendingNotificationRoutes}
          saveStatus={activeSaveStatus}
          persistedValuesByKey={persistedValuesByKey}
          configVersion={configVersion}
          onBindEvents={(routingValue, kinds) => {
            for (const update of buildNotificationEventBindingUpdates(
              allValuesByKey,
              routingValue,
              kinds,
            )) {
              setDraftValue(update.key, update.value);
            }
          }}
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
      ) : isAgentBehaviorPanel ? (
        <AgentBehaviorPanel
          items={subFilteredItems}
          disabled={isSaving}
          onChange={setDraftValue}
          onBatchChange={applyPartialUpdate}
          onResetKeys={resetDraftKeys}
          issueByKey={issueByKey}
          draftValuesByKey={allValuesByKey}
          persistedValuesByKey={persistedValuesByKey}
          saveStatus={activeSaveStatus}
          modelSummary={agentModelSummary}
          essentialsFocus={agentEssentialsFocus}
          fieldGroups={activeFieldGroupOrder ?? []}
          fieldGroupIdOf={fieldGroupIdOf}
          fieldGroupOrderOf={fieldGroupOrderOf}
          readOnlyDiagnosticForItem={readOnlyDiagnosticForItem}
        />
      ) : activeFieldGroupOrder ? (
        <div className="space-y-4">
          <Suspense fallback={null}>
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
              <SettingsFieldGroupPanel
                key={group.id}
                group={group}
                groupItems={groupItems}
                revealFieldKey={revealFieldKey}
                revealRequestId={revealRequestId}
                showChannelRoutingEmptyBanner={showChannelRoutingEmptyBanner}
                channelRoutingEmptyBanner={channelRoutingEmptyBanner}
                isSaving={isSaving}
                setDraftValue={setDraftValue}
                issueByKey={issueByKey}
                allValuesByKey={allValuesByKey}
                readOnlyDiagnosticForItem={readOnlyDiagnosticForItem}
                activeCategory={activeCategory}
                channelRoutingFieldKeys={channelRoutingFieldKeys}
                hasConfiguredNotificationChannelStatus={hasConfiguredNotificationChannelStatus}
                channelRoutingOptionFilter={channelRoutingOptionFilter}
                channelRoutingEmptyState={channelRoutingEmptyState}
                Field={SettingsField}
              />
            );
          })}
          </Suspense>
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
