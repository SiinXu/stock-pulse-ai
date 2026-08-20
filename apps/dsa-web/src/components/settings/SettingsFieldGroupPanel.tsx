// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect, useState, type ComponentType, type ReactNode } from 'react';
import { Collapsible } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { ConfigValidationIssue, SystemConfigItem } from '../../types/systemConfig';
import {
  isFieldEnabledByContract,
  resolveFieldRequirement,
} from '../../utils/configConditions';
import {
  isSettingsGroupDefaultOpen,
  resolveSettingsRevealFieldKey,
  settingsRevealUrlFingerprint,
  type FieldGroupDescriptor,
} from './settingsFieldGroupDisclosure';
import type { SettingsFieldProps } from './settingsFieldMemo';

export type SettingsFieldGroupPanelProps = {
  group: FieldGroupDescriptor;
  groupItems: SystemConfigItem[];
  revealFieldKey?: string | null;
  revealRequestId?: number | null;
  showChannelRoutingEmptyBanner: boolean;
  channelRoutingEmptyBanner: ReactNode;
  isSaving: boolean;
  setDraftValue: (key: string, value: string) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  allValuesByKey: Record<string, string>;
  readOnlyDiagnosticForItem: (item: SystemConfigItem, categoryHint?: string) => string | undefined;
  activeCategory: string;
  channelRoutingFieldKeys: Set<string>;
  hasConfiguredNotificationChannelStatus: boolean;
  channelRoutingOptionFilter: (optionValue: string) => boolean;
  channelRoutingEmptyState: ReactNode;
  Field: ComponentType<SettingsFieldProps>;
};

export function SettingsFieldGroupPanel({
  group,
  groupItems,
  revealFieldKey,
  revealRequestId = null,
  showChannelRoutingEmptyBanner,
  channelRoutingEmptyBanner,
  isSaving,
  setDraftValue,
  issueByKey,
  allValuesByKey,
  readOnlyDiagnosticForItem,
  activeCategory,
  channelRoutingFieldKeys,
  hasConfiguredNotificationChannelStatus,
  channelRoutingOptionFilter,
  channelRoutingEmptyState,
  Field,
}: SettingsFieldGroupPanelProps) {
  const { t } = useUiLanguage();
  const defaultOpen = isSettingsGroupDefaultOpen(group.id);
  const shouldReveal = Boolean(revealFieldKey)
    && groupItems.some((item) => item.key === revealFieldKey);

  return (
    <div
      data-testid={`settings-field-group-${group.id}`}
      data-settings-field-group={group.id}
    >
      <Collapsible
        key={`${group.id}:${shouldReveal ? `${revealFieldKey}:${revealRequestId ?? 'url'}` : 'rest'}`}
        title={t(group.titleKey)}
        defaultOpen={defaultOpen || shouldReveal}
      >
        {showChannelRoutingEmptyBanner ? channelRoutingEmptyBanner : null}
        <form onSubmit={(event) => event.preventDefault()}>
          {groupItems.map((item) => (
            <Field
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
      </Collapsible>
    </div>
  );
}

export type SettingsFieldGroupsProps = {
  groups: FieldGroupDescriptor[];
  items: SystemConfigItem[];
  fieldGroupIdOf: (key: string) => string;
  fieldGroupOrderOf: (key: string) => number;
  queryField?: string | null;
  revealRequestKey?: string | null;
  revealRequestId?: number | null;
  showChannelRoutingEmptyBannerFor: (groupItems: SystemConfigItem[]) => boolean;
  channelRoutingEmptyBanner: ReactNode;
  isSaving: boolean;
  setDraftValue: (key: string, value: string) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  allValuesByKey: Record<string, string>;
  readOnlyDiagnosticForItem: (item: SystemConfigItem, categoryHint?: string) => string | undefined;
  activeCategory: string;
  channelRoutingFieldKeys: Set<string>;
  hasConfiguredNotificationChannelStatus: boolean;
  channelRoutingOptionFilter: (optionValue: string) => boolean;
  channelRoutingEmptyState: ReactNode;
  Field: ComponentType<SettingsFieldProps>;
};

export default function SettingsFieldGroups({
  groups,
  items,
  fieldGroupIdOf,
  fieldGroupOrderOf,
  queryField = null,
  revealRequestKey = null,
  revealRequestId = null,
  showChannelRoutingEmptyBannerFor,
  channelRoutingEmptyBanner,
  isSaving,
  setDraftValue,
  issueByKey,
  allValuesByKey,
  readOnlyDiagnosticForItem,
  activeCategory,
  channelRoutingFieldKeys,
  hasConfiguredNotificationChannelStatus,
  channelRoutingOptionFilter,
  channelRoutingEmptyState,
  Field,
}: SettingsFieldGroupsProps) {
  const [hash, setHash] = useState(
    () => (typeof window === 'undefined' ? '' : window.location.hash),
  );
  const [requestSnapshot, setRequestSnapshot] = useState<{
    requestId: number;
    fingerprint: string;
  } | null>(null);

  useEffect(() => {
    const syncHash = () => setHash(window.location.hash);
    window.addEventListener('hashchange', syncHash);
    return () => window.removeEventListener('hashchange', syncHash);
  }, []);

  if (revealRequestId != null && revealRequestId !== requestSnapshot?.requestId) {
    setRequestSnapshot({
      requestId: revealRequestId,
      fingerprint: settingsRevealUrlFingerprint(queryField, hash),
    });
  }

  const revealFieldKey = resolveSettingsRevealFieldKey({
    requestKey: revealRequestKey,
    requestUrlFingerprint: requestSnapshot?.fingerprint,
    queryField,
    hash,
  });

  return (
    <div className="space-y-4">
      {groups.map((group) => {
        const groupItems = items
          .filter((item) => fieldGroupIdOf(item.key) === group.id)
          .sort((a, b) => fieldGroupOrderOf(a.key) - fieldGroupOrderOf(b.key));
        if (!groupItems.length) {
          return null;
        }
        return (
          <SettingsFieldGroupPanel
            key={group.id}
            group={group}
            groupItems={groupItems}
            revealFieldKey={revealFieldKey}
            revealRequestId={revealRequestId}
            showChannelRoutingEmptyBanner={showChannelRoutingEmptyBannerFor(groupItems)}
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
            Field={Field}
          />
        );
      })}
    </div>
  );
}
