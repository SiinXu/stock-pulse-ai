// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { AvailableModelEntry, LlmProviderCatalogEntry } from '../../types/systemConfig';
import type { UiLanguage } from '../../i18n/uiText';
import type { SearchableSelectOption } from '../common';
import { decodeModelRef } from '../../utils/modelRef';
import { getProviderDisplayLabel } from './llmConnectionContract';

export const TASK_MODEL_KEYS = new Set(['LITELLM_MODEL', 'AGENT_LITELLM_MODEL', 'VISION_MODEL']);

export function buildModelSelectorOptions(
  availableModels: AvailableModelEntry[],
  providerCatalog: LlmProviderCatalogEntry[],
  uiLanguage: UiLanguage,
): SearchableSelectOption[] {
  return availableModels.map((entry) => {
    const connectionLabel = entry.connectionName ?? entry.connection ?? entry.connectionId;
    const catalogProvider = providerCatalog.find((provider) => provider.id === entry.providerId);
    const providerLabel = catalogProvider
      ? getProviderDisplayLabel(catalogProvider, uiLanguage)
      : entry.providerLabel ?? entry.provider;
    const sublabel = providerLabel && connectionLabel && providerLabel !== connectionLabel
      ? `${providerLabel} · ${connectionLabel}`
      : providerLabel ?? connectionLabel ?? undefined;
    return {
      value: entry.modelRef || entry.route,
      label: entry.display || entry.route,
      sublabel,
      group: connectionLabel ?? providerLabel ?? undefined,
      keywords: [entry.route, entry.modelRef, entry.providerId, connectionLabel]
        .filter((part): part is string => Boolean(part)),
    };
  });
}

export function buildAvailableModelRefSet(availableModels: AvailableModelEntry[]): Set<string> {
  return new Set(availableModels.map((entry) => entry.modelRef || entry.route));
}

export function buildAvailableModelsByRoute(
  availableModels: AvailableModelEntry[],
): Map<string, AvailableModelEntry[]> {
  const byRoute = new Map<string, AvailableModelEntry[]>();
  for (const entry of availableModels) {
    const entries = byRoute.get(entry.route) ?? [];
    entries.push(entry);
    byRoute.set(entry.route, entries);
  }
  return byRoute;
}

export function resolveConfiguredModelRef(
  value: string,
  availableModelRefSet: Set<string>,
  availableModelsByRoute: Map<string, AvailableModelEntry[]>,
): string {
  const normalized = value.trim();
  if (!normalized || availableModelRefSet.has(normalized)) {
    return normalized;
  }
  const matches = availableModelsByRoute.get(normalized) ?? [];
  return matches.length === 1 ? (matches[0].modelRef || matches[0].route) : normalized;
}

export function formatConfiguredModel(
  value: string,
  availableModels: AvailableModelEntry[],
  resolveRef: (value: string) => string,
): string {
  const resolved = resolveRef(value);
  const entry = availableModels.find((model) => (model.modelRef || model.route) === resolved);
  if (!entry) {
    const decoded = decodeModelRef(value);
    return decoded ? `${decoded.runtimeRoute} · ${decoded.connectionId}` : value.trim();
  }
  const connectionLabel = entry.connectionName ?? entry.connection ?? entry.connectionId;
  return connectionLabel ? `${entry.display} · ${connectionLabel}` : entry.display;
}
