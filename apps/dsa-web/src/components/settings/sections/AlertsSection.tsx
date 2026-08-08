// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable @typescript-eslint/no-explicit-any -- mechanical section props accept page model shapes */
import type React from 'react';
import type { SystemConfigItem } from '../../../types/systemConfig';
import { SettingsField, SettingsSectionCard } from '..';
import {
  isFieldEnabledByContract,
  resolveFieldRequirement,
} from '../../../utils/configConditions';

export type AlertsSectionProps = {
  isAlertsSection: boolean;
  activeView: string;
  eventMonitorItems: SystemConfigItem[];
  settingsText: { eventMonitor: string; eventMonitorDescription: string };
  isSaving: boolean;
  setDraftValue: (key: string, value: string) => void;
  issueByKey: Record<string, any>;
  allValuesByKey: Record<string, string>;
  readOnlyDiagnosticForItem: (item: SystemConfigItem, category?: string) => string | undefined;
};

export const AlertsSection: React.FC<AlertsSectionProps> = (p) => (
  p.isAlertsSection && p.activeView === 'events' && p.eventMonitorItems.length > 0 ? (
    <SettingsSectionCard
      title={p.settingsText.eventMonitor}
      description={p.settingsText.eventMonitorDescription}
    >
      <form
        className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]"
        onSubmit={(event) => event.preventDefault()}
      >
        {p.eventMonitorItems.map((item) => (
          <SettingsField
            key={item.key}
            item={item}
            value={item.value}
            disabled={p.isSaving}
            onChange={p.setDraftValue}
            issues={p.issueByKey[item.key] || []}
            requirement={resolveFieldRequirement(item.schema?.contract, p.allValuesByKey)}
            dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, p.allValuesByKey)}
            readOnlyDiagnostic={p.readOnlyDiagnosticForItem(item, 'agent') as any}
          />
        ))}
      </form>
    </SettingsSectionCard>
  ) : null
);
