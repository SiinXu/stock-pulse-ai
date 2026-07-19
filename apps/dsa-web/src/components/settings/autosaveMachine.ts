// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { SystemConfigUpdateItem } from '../../types/systemConfig';

/**
 * Explicit lifecycle for a Settings group's autosave.
 *
 * - `idle`      no pending edits for the group.
 * - `dirty`     pending edits exist but cannot be scheduled yet (autosave is
 *               paused, e.g. while a version conflict is being resolved).
 * - `scheduled` a debounced save is queued (or waiting on the Provider Catalog).
 * - `saving`    the network write is in flight.
 * - `saved`     the last write succeeded.
 * - `conflicted` the write was rejected by an optimistic version conflict.
 * - `failed`    validation or the write failed; the same content will not retry
 *               automatically.
 */
export type SettingsSaveStatus =
  | 'idle'
  | 'dirty'
  | 'scheduled'
  | 'saving'
  | 'saved'
  | 'conflicted'
  | 'failed';

export interface SettingsGroupSaveState {
  status: SettingsSaveStatus;
  fingerprint: string;
}

/** Debounce applied before a scheduled group is persisted. */
export const SETTINGS_AUTOSAVE_DEBOUNCE_MS = 700;

/** Content signature used to detect whether a group's pending edits changed. */
export function computeGroupFingerprint(items: SystemConfigUpdateItem[]): string {
  return JSON.stringify(items);
}

/** Inputs that gate whether the `ai_model` group is safe to persist. */
export interface AiModelSaveGate {
  catalogLoading: boolean;
  catalogError: boolean;
  schemaUnavailable: boolean;
  channelDraftValid: boolean;
  changesConnection: boolean;
  connectionRespectsSchema: boolean;
}

/**
 * Pure pre-save gate for the `ai_model` group.
 *
 * Returns the blocking status when the draft cannot proceed, or `null` when it
 * is clear to persist. `checkConnection` enforces the Connection schema
 * contract: the scheduling pass leaves connection edits schedulable (they
 * debounce first), while the run pass enforces the contract immediately before
 * the network write.
 */
export function classifyAiModelGate(
  gate: AiModelSaveGate,
  options: { checkConnection: boolean },
): Extract<SettingsSaveStatus, 'scheduled' | 'failed'> | null {
  if (gate.catalogLoading || gate.catalogError) {
    return 'scheduled';
  }
  if (gate.schemaUnavailable) {
    return 'failed';
  }
  if (!gate.channelDraftValid) {
    return 'failed';
  }
  if (options.checkConnection && gate.changesConnection && !gate.connectionRespectsSchema) {
    return 'failed';
  }
  return null;
}
