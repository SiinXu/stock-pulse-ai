// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Agent Behavior section panel: preset-first setup + progressive disclosure
 * for the remaining fields (issue #868 / #877 density).
 *
 * Writes go through the existing draft `onChange` path — no parallel config
 * store and no backend schema changes.
 */
import { useMemo, useState } from 'react';
import type React from 'react';
import { ChevronDown } from 'lucide-react';
import type { ConfigValidationIssue, SystemConfigItem } from '../../types/systemConfig';
import {
  isFieldEnabledByContract,
  resolveFieldRequirement,
} from '../../utils/configConditions';
import { Badge, Button } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { SettingsField } from './SettingsField';
import {
  AGENT_ESSENTIAL_KEYS,
  AGENT_SETUP_COPY,
  AGENT_SETUP_PRESETS,
  type AgentSetupPresetId,
  buildAgentPresetUpdates,
  diffAgentPreset,
  formatAgentPresetValue,
  isAgentEssentialKey,
  resolveAgentPresetStatus,
} from './agentSetupPresets';

export type AgentBehaviorPanelProps = {
  items: SystemConfigItem[];
  disabled: boolean;
  onChange: (key: string, value: string) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  allValuesByKey: Record<string, string>;
  readOnlyDiagnosticForItem?: (item: SystemConfigItem, categoryHint?: string) => string | undefined;
};

function sortByEssentialOrder(items: SystemConfigItem[]): SystemConfigItem[] {
  const order = new Map(AGENT_ESSENTIAL_KEYS.map((key, index) => [key, index]));
  return [...items].sort((left, right) => {
    const leftOrder = order.get(left.key as (typeof AGENT_ESSENTIAL_KEYS)[number]) ?? Number.MAX_SAFE_INTEGER;
    const rightOrder = order.get(right.key as (typeof AGENT_ESSENTIAL_KEYS)[number]) ?? Number.MAX_SAFE_INTEGER;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return (left.schema?.displayOrder ?? 0) - (right.schema?.displayOrder ?? 0);
  });
}

function normalizeNeedsWrite(current: string | undefined, next: string): boolean {
  return String(current ?? '').trim() !== String(next ?? '').trim();
}

export const AgentBehaviorPanel: React.FC<AgentBehaviorPanelProps> = ({
  items,
  disabled,
  onChange,
  issueByKey,
  allValuesByKey,
  readOnlyDiagnosticForItem,
}) => {
  const { language } = useUiLanguage();
  const copy = AGENT_SETUP_COPY[language];
  const [lastAppliedPresetId, setLastAppliedPresetId] = useState<AgentSetupPresetId | null>(null);
  const [lastAppliedChanges, setLastAppliedChanges] = useState<Array<{
    key: string;
    from: string;
    to: string;
  }> | null>(null);
  const [previewPresetId, setPreviewPresetId] = useState<AgentSetupPresetId | null>(null);

  const availableKeySet = useMemo(
    () => new Set(items.map((item) => item.key.toUpperCase())),
    [items],
  );

  const essentialItems = useMemo(
    () => sortByEssentialOrder(items.filter((item) => isAgentEssentialKey(item.key))),
    [items],
  );
  const advancedItems = useMemo(
    () => items
      .filter((item) => !isAgentEssentialKey(item.key))
      .sort((a, b) => (a.schema?.displayOrder ?? 0) - (b.schema?.displayOrder ?? 0)),
    [items],
  );

  const status = useMemo(
    () => resolveAgentPresetStatus(allValuesByKey, {
      availableKeys: availableKeySet,
      lastAppliedPresetId,
    }),
    [allValuesByKey, availableKeySet, lastAppliedPresetId],
  );

  const statusLabel = useMemo(() => {
    if (status.kind === 'exact') {
      return `${copy.active}: ${copy[status.presetId].name}`;
    }
    if (status.basePresetId) {
      return copy.customBasedOn.replace('{name}', copy[status.basePresetId].name);
    }
    return copy.unmatched;
  }, [copy, status]);

  const previewChanges = useMemo(() => {
    if (!previewPresetId) {
      return [];
    }
    return diffAgentPreset(previewPresetId, allValuesByKey, availableKeySet);
  }, [previewPresetId, allValuesByKey, availableKeySet]);

  const applyPreset = (presetId: AgentSetupPresetId) => {
    const changes = diffAgentPreset(presetId, allValuesByKey, availableKeySet);
    const updates = buildAgentPresetUpdates(presetId, availableKeySet);
    for (const update of updates) {
      if (normalizeNeedsWrite(allValuesByKey[update.key], update.value)) {
        onChange(update.key, update.value);
      }
    }
    setLastAppliedPresetId(presetId);
    setLastAppliedChanges(changes);
    setPreviewPresetId(presetId);
  };

  const renderField = (item: SystemConfigItem) => (
    <SettingsField
      key={item.key}
      item={item}
      value={item.value}
      disabled={disabled}
      onChange={onChange}
      issues={issueByKey[item.key] || []}
      requirement={resolveFieldRequirement(item.schema?.contract, allValuesByKey)}
      dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, allValuesByKey)}
      readOnlyDiagnostic={readOnlyDiagnosticForItem?.(item, 'agent')}
    />
  );

  return (
    <div className="space-y-4" data-testid="agent-behavior-panel">
      <section
        className="space-y-3 rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4"
        data-testid="agent-setup-presets"
        aria-labelledby="agent-setup-presets-title"
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 space-y-1">
            <h3 id="agent-setup-presets-title" className="text-sm font-semibold text-foreground">
              {copy.presetsTitle}
            </h3>
            <p className="text-xs leading-5 text-muted-text">{copy.presetsDescription}</p>
          </div>
          <Badge
            variant={status.kind === 'exact' ? 'success' : 'warning'}
            size="sm"
            data-testid="agent-preset-status"
          >
            {statusLabel}
          </Badge>
        </div>

        <div className="grid gap-2 sm:grid-cols-3" role="list">
          {AGENT_SETUP_PRESETS.map((preset) => {
            const isExact = status.kind === 'exact' && status.presetId === preset.id;
            const isPreview = previewPresetId === preset.id;
            return (
              <div
                key={preset.id}
                role="listitem"
                className={cn(
                  'flex flex-col gap-2 rounded-lg border px-3 py-3 transition-colors',
                  isExact
                    ? 'border-success/40 bg-success/5'
                    : 'border-[var(--settings-border)] bg-background/35',
                )}
                data-testid={`agent-preset-card-${preset.id}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 space-y-1">
                    <p className="text-sm font-medium text-foreground">{copy[preset.id].name}</p>
                    <p className="text-xs leading-5 text-muted-text">{copy[preset.id].description}</p>
                  </div>
                  {preset.recommended ? (
                    <Badge variant="info" size="sm">{copy.recommended}</Badge>
                  ) : null}
                </div>
                <Button
                  type="button"
                  variant={isExact ? 'secondary' : 'primary'}
                  size="compact"
                  disabled={disabled || isExact}
                  onClick={() => applyPreset(preset.id)}
                  onFocus={() => setPreviewPresetId(preset.id)}
                  onMouseEnter={() => setPreviewPresetId(preset.id)}
                  data-testid={`agent-preset-apply-${preset.id}`}
                >
                  {isExact ? copy.active : copy.apply}
                </Button>
                {isPreview && !isExact ? (
                  <div
                    className="rounded-md border border-[var(--settings-border-soft)] bg-background/50 px-2 py-2"
                    data-testid={`agent-preset-preview-${preset.id}`}
                  >
                    <p className="text-xxs font-medium uppercase tracking-wide text-muted-text">
                      {copy.changesTitle}
                    </p>
                    {previewChanges.length === 0 ? (
                      <p className="mt-1 text-xs text-secondary-text">{copy.noChanges}</p>
                    ) : (
                      <ul className="mt-1 max-h-28 space-y-0.5 overflow-y-auto text-xs text-secondary-text">
                        {previewChanges.map((change) => (
                          <li key={change.key}>
                            {copy.fieldChange
                              .replace('{key}', change.key)
                              .replace('{from}', formatAgentPresetValue(change.from, copy.emptyValue))
                              .replace('{to}', formatAgentPresetValue(change.to, copy.emptyValue))}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>

        {lastAppliedChanges && lastAppliedChanges.length > 0 ? (
          <div
            className="rounded-md border border-success/25 bg-success/5 px-3 py-2"
            data-testid="agent-preset-last-applied"
            aria-live="polite"
          >
            <p className="text-xs font-medium text-foreground">{copy.changesTitle}</p>
            <ul className="mt-1 max-h-32 space-y-0.5 overflow-y-auto text-xs text-secondary-text">
              {lastAppliedChanges.map((change) => (
                <li key={change.key}>
                  {copy.fieldChange
                    .replace('{key}', change.key)
                    .replace('{from}', formatAgentPresetValue(change.from, copy.emptyValue))
                    .replace('{to}', formatAgentPresetValue(change.to, copy.emptyValue))}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="space-y-2" data-testid="agent-essentials-fields">
        <h3 className="px-1 text-sm font-medium text-secondary-text">{copy.essentialsTitle}</h3>
        {essentialItems.length ? (
          <form
            className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-1"
            onSubmit={(event) => event.preventDefault()}
          >
            {essentialItems.map(renderField)}
          </form>
        ) : null}
      </section>

      {advancedItems.length ? (
        <details
          className="group/agent-advanced overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] transition-colors duration-200 hover:bg-[var(--settings-surface-hover)]"
          data-testid="agent-advanced-fields"
        >
          <summary className="flex cursor-pointer list-none items-start justify-between gap-3 px-4 py-4 [&::-webkit-details-marker]:hidden">
            <div className="min-w-0 space-y-1">
              <p className="text-sm font-semibold text-foreground">{copy.advancedTitle}</p>
              <p className="text-xs leading-5 text-muted-text">{copy.advancedDescription}</p>
            </div>
            <ChevronDown
              className="mt-0.5 h-4 w-4 shrink-0 text-muted-text transition-transform group-open/agent-advanced:rotate-180"
              aria-hidden="true"
            />
          </summary>
          <form
            className="border-t border-[var(--settings-border-soft)] p-1"
            onSubmit={(event) => event.preventDefault()}
          >
            {advancedItems.map(renderField)}
          </form>
        </details>
      ) : null}
    </div>
  );
};

export default AgentBehaviorPanel;
