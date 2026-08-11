// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Agent Behavior section panel: safe preset-first setup with persisted status
 * and registry-owned progressive disclosure.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type React from 'react';
import { ChevronDown } from 'lucide-react';
import type { ConfigValidationIssue, SystemConfigItem } from '../../types/systemConfig';
import type { UiTextKey } from '../../i18n/uiText';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { resolveSettingsFieldTitle } from '../../locales/settingsFieldTitle';
import {
  isFieldEnabledByContract,
  resolveFieldRequirement,
} from '../../utils/configConditions';
import { cn } from '../../utils/cn';
import { Badge, Button, ConfirmDialog } from '../common';
import type { SettingsSaveStatus } from './autosaveMachine';
// Import through the settings barrel so the real Settings host test harness can
// substitute its field adapter while production still resolves the same export.
import { SettingsField } from './index';
import {
  AGENT_ESSENTIAL_KEYS,
  AGENT_PRESET_MANAGED_KEYS,
  AGENT_SETUP_COPY,
  AGENT_SETUP_PRESETS,
  type AgentPresetFieldChange,
  type AgentSetupPresetId,
  buildAgentPresetUpdates,
  diffAgentPreset,
  formatAgentPresetValue,
  isAgentEssentialKey,
  resolveAgentPresetStatus,
} from './agentSetupPresets';

export type AgentModelSummary = {
  value: string;
  source: 'explicit' | 'inherited';
  readiness: 'ready' | 'checking' | 'unavailable' | 'unconfigured' | 'unknown';
};

export type AgentBehaviorPanelProps = {
  items: SystemConfigItem[];
  disabled: boolean;
  onChange: (key: string, value: string) => void;
  onBatchChange: (items: Array<{ key: string; value: string }>) => void;
  onResetKeys: (keys: string[]) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  draftValuesByKey: Record<string, string>;
  persistedValuesByKey: Record<string, string>;
  saveStatus: SettingsSaveStatus;
  modelSummary: AgentModelSummary;
  fieldGroups: Array<{ id: string; titleKey: UiTextKey }>;
  fieldGroupIdOf: (key: string) => string;
  fieldGroupOrderOf: (key: string) => number;
  readOnlyDiagnosticForItem?: (item: SystemConfigItem, categoryHint?: string) => string | undefined;
};

function sortByEssentialOrder(items: SystemConfigItem[]): SystemConfigItem[] {
  const order = new Map(AGENT_ESSENTIAL_KEYS.map((key, index) => [key, index]));
  return [...items].sort((left, right) => {
    const leftOrder = order.get(left.key as (typeof AGENT_ESSENTIAL_KEYS)[number]) ?? Number.MAX_SAFE_INTEGER;
    const rightOrder = order.get(right.key as (typeof AGENT_ESSENTIAL_KEYS)[number]) ?? Number.MAX_SAFE_INTEGER;
    return leftOrder !== rightOrder
      ? leftOrder - rightOrder
      : (left.schema?.displayOrder ?? 0) - (right.schema?.displayOrder ?? 0);
  });
}

function normalize(value: string | undefined): string {
  return String(value ?? '').trim();
}

export const AgentBehaviorPanel: React.FC<AgentBehaviorPanelProps> = ({
  items,
  disabled,
  onChange,
  onBatchChange,
  onResetKeys,
  issueByKey,
  draftValuesByKey,
  persistedValuesByKey,
  saveStatus,
  modelSummary,
  fieldGroups,
  fieldGroupIdOf,
  fieldGroupOrderOf,
  readOnlyDiagnosticForItem,
}) => {
  const { language, t } = useUiLanguage();
  const copy = AGENT_SETUP_COPY[language];
  const [previewPresetId, setPreviewPresetId] = useState<AgentSetupPresetId | null>(null);
  const [confirmPresetId, setConfirmPresetId] = useState<AgentSetupPresetId | null>(null);
  const [draftPresetId, setDraftPresetId] = useState<AgentSetupPresetId | null>(null);
  const [draftPresetChanges, setDraftPresetChanges] = useState<AgentPresetFieldChange[]>([]);
  const presetTriggerRef = useRef<HTMLButtonElement | null>(null);
  const restorePresetFocusRef = useRef(false);

  useEffect(() => {
    if (!confirmPresetId && restorePresetFocusRef.current) {
      restorePresetFocusRef.current = false;
      presetTriggerRef.current?.focus();
    }
  }, [confirmPresetId]);

  const availableKeySet = useMemo(
    () => new Set(items.map((item) => item.key.toUpperCase())),
    [items],
  );
  const fullySupported = AGENT_PRESET_MANAGED_KEYS.every((key) => availableKeySet.has(key));
  const itemByKey = useMemo(
    () => new Map(items.map((item) => [item.key.toUpperCase(), item])),
    [items],
  );
  const essentialItems = useMemo(
    () => sortByEssentialOrder(items.filter((item) => isAgentEssentialKey(item.key))),
    [items],
  );
  const advancedItems = useMemo(
    () => items.filter((item) => !isAgentEssentialKey(item.key)),
    [items],
  );
  const persistedStatus = useMemo(
    () => resolveAgentPresetStatus(persistedValuesByKey, { availableKeys: availableKeySet }),
    [availableKeySet, persistedValuesByKey],
  );

  const changesFor = (presetId: AgentSetupPresetId | null) => (
    presetId ? diffAgentPreset(presetId, draftValuesByKey, availableKeySet) : []
  );
  const previewChanges = useMemo(
    () => changesFor(previewPresetId),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [previewPresetId, draftValuesByKey, availableKeySet],
  );
  const confirmChanges = useMemo(
    () => changesFor(confirmPresetId),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [confirmPresetId, draftValuesByKey, availableKeySet],
  );

  const fieldLabel = (key: string): string => {
    const item = itemByKey.get(key.toUpperCase());
    return resolveSettingsFieldTitle({
      itemKey: key,
      schemaKey: item?.schema?.key,
      fallbackTitle: item?.schema?.title,
      language,
    });
  };

  const renderChanges = (changes: AgentPresetFieldChange[]) => (
    <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-xs text-secondary-text">
      {changes.map((change) => (
        <li key={change.key}>
          <span className="font-medium text-foreground">{fieldLabel(change.key)}</span>
          {': '}
          <span>{formatAgentPresetValue(change.from, copy.emptyValue)}</span>
          <span aria-hidden="true"> → </span>
          <span>{formatAgentPresetValue(change.to, copy.emptyValue)}</span>
        </li>
      ))}
    </ul>
  );

  const confirmPreset = () => {
    if (!confirmPresetId) return;
    const updates = buildAgentPresetUpdates(confirmPresetId, availableKeySet)
      .filter((update) => normalize(draftValuesByKey[update.key]) !== normalize(update.value));
    onBatchChange(updates);
    setDraftPresetId(confirmPresetId);
    setDraftPresetChanges(confirmChanges);
    setPreviewPresetId(confirmPresetId);
    restorePresetFocusRef.current = true;
    setConfirmPresetId(null);
  };

  const cancelPresetConfirmation = () => {
    restorePresetFocusRef.current = true;
    setConfirmPresetId(null);
  };

  const resetPresetDraft = () => {
    onResetKeys(draftPresetChanges.map((change) => change.key));
    setDraftPresetId(null);
    setDraftPresetChanges([]);
  };

  let statusLabel = copy.unmatched;
  let statusVariant: React.ComponentProps<typeof Badge>['variant'] = 'warning';
  if (!fullySupported) {
    statusLabel = copy.unsupported;
  } else if (saveStatus === 'failed' && draftPresetId) {
    statusLabel = `${copy.failed}: ${copy[draftPresetId].name}`;
    statusVariant = 'danger';
  } else if (saveStatus === 'conflicted' && draftPresetId) {
    statusLabel = `${copy.conflicted}: ${copy[draftPresetId].name}`;
    statusVariant = 'danger';
  } else if (
    draftPresetId
    && (
      ['dirty', 'scheduled', 'saving'].includes(saveStatus)
      || persistedStatus.kind !== 'exact'
      || persistedStatus.presetId !== draftPresetId
    )
  ) {
    statusLabel = `${copy.pending}: ${copy[draftPresetId].name}`;
    statusVariant = 'info';
  } else if (persistedStatus.kind === 'exact') {
    statusLabel = `${copy.active}: ${copy[persistedStatus.presetId].name}`;
    statusVariant = 'success';
  } else if (persistedStatus.basePresetId) {
    statusLabel = copy.customBasedOn.replace('{name}', copy[persistedStatus.basePresetId].name);
  }

  const modelReadinessLabel = persistedValuesByKey.AGENT_FEATURES_ACKNOWLEDGED_OFF === 'true'
    ? copy.agentAcknowledgedOff
    : modelSummary.readiness === 'ready'
      ? copy.modelReady
      : modelSummary.readiness === 'checking'
        ? copy.modelChecking
      : modelSummary.readiness === 'unavailable'
          ? copy.modelUnavailable
          : modelSummary.readiness === 'unknown'
            ? copy.modelUnknown
          : copy.modelNotConfigured;

  const renderField = (item: SystemConfigItem) => (
    <SettingsField
      key={item.key}
      item={item}
      value={item.value}
      disabled={disabled}
      onChange={onChange}
      issues={issueByKey[item.key] || []}
      requirement={resolveFieldRequirement(item.schema?.contract, draftValuesByKey)}
      dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, draftValuesByKey)}
      readOnlyDiagnostic={readOnlyDiagnosticForItem?.(item, 'agent')}
    />
  );

  return (
    <div className="space-y-4" data-testid="agent-behavior-panel">
      <section className="space-y-3 rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4" data-testid="agent-active-summary">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h3 className="text-sm font-semibold text-foreground">{copy.summaryTitle}</h3>
          <Badge variant={statusVariant} size="sm" data-testid="agent-preset-status">{statusLabel}</Badge>
        </div>
        <dl className="grid gap-2 text-xs sm:grid-cols-3">
          <div><dt className="font-medium text-foreground">{copy.model}</dt><dd className="text-secondary-text">{modelSummary.value || copy.modelNotConfigured} · {modelSummary.source === 'explicit' ? copy.explicitModel : copy.inheritedModel} · {modelReadinessLabel}</dd></div>
          <div><dt className="font-medium text-foreground">{copy.hitl}</dt><dd className="text-secondary-text">{persistedValuesByKey.AGENT_RISK_OVERRIDE === 'true' ? copy.hitlEnabled : copy.hitlDisabled}</dd></div>
          <div><dt className="font-medium text-foreground">{copy.deepTools}</dt><dd className="text-secondary-text">{persistedValuesByKey.VALUATION_AGENT_TOOL_ENABLED === 'true' ? copy.deepToolsEnabled : copy.deepToolsDisabled}</dd></div>
        </dl>
        {draftPresetId && (saveStatus === 'failed' || saveStatus === 'conflicted') ? (
          <Button type="button" variant="secondary" size="compact" onClick={resetPresetDraft}>{copy.reset}</Button>
        ) : null}
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4" data-testid="agent-setup-presets" aria-labelledby="agent-setup-presets-title">
        <div className="space-y-1">
          <h3 id="agent-setup-presets-title" className="text-sm font-semibold text-foreground">{copy.presetsTitle}</h3>
          <p className="text-xs leading-5 text-muted-text">{copy.presetsDescription}</p>
        </div>
        <div className="grid gap-2 sm:grid-cols-3" role="list">
          {AGENT_SETUP_PRESETS.map((preset) => {
            const isExact = fullySupported && persistedStatus.kind === 'exact' && persistedStatus.presetId === preset.id;
            const isPreview = previewPresetId === preset.id;
            return (
              <div key={preset.id} role="listitem" className={cn('flex flex-col gap-2 rounded-lg border px-3 py-3', isExact ? 'border-success/40 bg-success/5' : 'border-[var(--settings-border)] bg-background/35')} data-testid={`agent-preset-card-${preset.id}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-1"><p className="text-sm font-medium text-foreground">{copy[preset.id].name}</p><p className="text-xs leading-5 text-muted-text">{copy[preset.id].description}</p></div>
                  {preset.recommended ? <Badge variant="info" size="sm">{copy.recommended}</Badge> : null}
                </div>
                <Button type="button" variant={isExact ? 'secondary' : 'primary'} size="compact" disabled={disabled || isExact || !fullySupported} onClick={(event) => { presetTriggerRef.current = event.currentTarget; setConfirmPresetId(preset.id); }} onFocus={() => setPreviewPresetId(preset.id)} onMouseEnter={() => setPreviewPresetId(preset.id)} data-testid={`agent-preset-apply-${preset.id}`}>
                  {isExact ? copy.active : copy.apply}
                </Button>
                {isPreview && !isExact ? (
                  <div className="rounded-md border border-[var(--settings-border-soft)] bg-background/50 px-2 py-2" data-testid={`agent-preset-preview-${preset.id}`}>
                    <p className="text-xxs font-medium uppercase tracking-wide text-muted-text">{copy.changesTitle}</p>
                    {previewChanges.length ? renderChanges(previewChanges) : <p className="mt-1 text-xs text-secondary-text">{copy.noChanges}</p>}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </section>

      <section className="space-y-2" data-testid="agent-essentials-fields">
        <h3 className="px-1 text-sm font-medium text-secondary-text">{copy.essentialsTitle}</h3>
        <form className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-1" onSubmit={(event) => event.preventDefault()}>{essentialItems.map(renderField)}</form>
      </section>

      {advancedItems.length ? (
        <details className="group/agent-advanced overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]" data-testid="agent-advanced-fields">
          <summary className="flex cursor-pointer list-none items-start justify-between gap-3 px-4 py-4 [&::-webkit-details-marker]:hidden"><div className="space-y-1"><p className="text-sm font-semibold text-foreground">{copy.advancedTitle}</p><p className="text-xs leading-5 text-muted-text">{copy.advancedDescription}</p></div><ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-text transition-transform group-open/agent-advanced:rotate-180" aria-hidden="true" /></summary>
          <div className="space-y-4 border-t border-[var(--settings-border-soft)] p-3">
            {fieldGroups.map((group) => {
              const groupItems = advancedItems.filter((item) => fieldGroupIdOf(item.key) === group.id).sort((a, b) => fieldGroupOrderOf(a.key) - fieldGroupOrderOf(b.key));
              return groupItems.length ? <div key={group.id} className="space-y-2"><h4 className="px-1 text-sm font-medium text-secondary-text">{t(group.titleKey)}</h4><form className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-background/25 p-1" onSubmit={(event) => event.preventDefault()}>{groupItems.map(renderField)}</form></div> : null;
            })}
          </div>
        </details>
      ) : null}

      <ConfirmDialog
        isOpen={Boolean(confirmPresetId)}
        title={confirmPresetId ? copy.confirmTitle.replace('{name}', copy[confirmPresetId].name) : ''}
        message={confirmPresetId ? <><p>{copy.confirmDescription.replace('{count}', String(confirmChanges.length))}</p><p className="mt-2 rounded-md border border-warning/30 bg-warning/10 p-2 text-warning">{copy.confirmWarnings}</p>{confirmChanges.length ? renderChanges(confirmChanges) : <p className="mt-2">{copy.noChanges}</p>}</> : ''}
        confirmText={copy.confirm}
        cancelText={copy.cancel}
        confirmDisabled={confirmChanges.length === 0}
        onConfirm={confirmPreset}
        onCancel={cancelPresetConfirmation}
      />
    </div>
  );
};

export default AgentBehaviorPanel;
