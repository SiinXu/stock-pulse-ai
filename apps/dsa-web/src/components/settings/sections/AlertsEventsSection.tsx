// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { ChevronDown } from 'lucide-react';
import {
  SettingsField,
  SettingsSectionCard,
} from '..';
import { isAgentExpertJsonKey } from '../agentSetupPresets';
import {
  isFieldEnabledByContract,
  resolveFieldRequirement,
} from '../../../utils/configConditions';
import type { UiLanguage } from '../../../i18n/uiText';
import { SETTINGS_PAGE_TEXT } from '../../../locales/settingsPage';
import { SETTINGS_MISC_TEXT } from '../../../locales/settingsMisc';
import type {
  ConfigValidationIssue,
  SystemConfigItem,
} from '../../../types/systemConfig';

type AlertsEventsSectionProps = {
  isAlertsSection: boolean;
  activeView: string;
  eventMonitorItems: SystemConfigItem[];
  uiLanguage: UiLanguage;
  isSaving: boolean;
  setDraftValue: (key: string, value: string) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  allValuesByKey: Record<string, string>;
  readOnlyDiagnosticForItem: (item: SystemConfigItem, categoryHint?: string) => string | undefined;
};

const AlertsEventsSection: React.FC<AlertsEventsSectionProps> = (props) => {
  const settingsText = SETTINGS_PAGE_TEXT[props.uiLanguage];
  if (!(props.isAlertsSection && props.activeView === 'events' && props.eventMonitorItems.length > 0)) {
    return null;
  }

  return (
    <SettingsSectionCard
      title={settingsText.eventMonitor}
      description={settingsText.eventMonitorDescription}
    >
      {(() => {
        const eventEssentials = props.eventMonitorItems.filter((item) => !isAgentExpertJsonKey(item.key));
        const eventExpertJson = props.eventMonitorItems.filter((item) => isAgentExpertJsonKey(item.key));
        const renderEventField = (item: (typeof props.eventMonitorItems)[number]) => (
          <SettingsField
            key={item.key}
            item={item}
            value={item.value}
            disabled={props.isSaving}
            onChange={props.setDraftValue}
            issues={props.issueByKey[item.key] || []}
            requirement={resolveFieldRequirement(item.schema?.contract, props.allValuesByKey)}
            dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, props.allValuesByKey)}
            readOnlyDiagnostic={props.readOnlyDiagnosticForItem(item, 'agent')}
          />
        );
        return (
          <div className="space-y-3">
            {eventEssentials.length ? (
              <form
                className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]"
                onSubmit={(event) => event.preventDefault()}
                data-testid="event-monitor-essentials"
              >
                {eventEssentials.map(renderEventField)}
              </form>
            ) : null}
            {eventExpertJson.length ? (
              <details
                className="group/event-expert overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]"
                data-testid="event-monitor-expert-json"
              >
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium text-foreground [&::-webkit-details-marker]:hidden">
                  <span>{SETTINGS_MISC_TEXT[props.uiLanguage].showAdvanced}</span>
                  <ChevronDown className="h-4 w-4 shrink-0 text-muted-text transition-transform group-open/event-expert:rotate-180" aria-hidden="true" />
                </summary>
                <form
                  className="border-t border-[var(--settings-border-soft)] p-1"
                  onSubmit={(event) => event.preventDefault()}
                >
                  {eventExpertJson.map(renderEventField)}
                </form>
              </details>
            ) : null}
          </div>
        );
      })()}
    </SettingsSectionCard>
  );
};

export default AlertsEventsSection;
