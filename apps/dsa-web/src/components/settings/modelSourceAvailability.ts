// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { ChannelTestState } from './llmChannelEditorModel';

/**
 * User-facing readiness for a model source.
 * "available" is reserved for enabled, complete sources without a known failed test.
 */
export type ModelSourceAvailability =
  | 'available'
  | 'unavailable'
  | 'untested'
  | 'testing'
  | 'disabled'
  | 'incomplete';

export type ModelSourceAvailabilityInput = {
  enabled: boolean;
  hasModels: boolean;
  issueCount: number;
  testState?: ChannelTestState | null;
};

export function resolveModelSourceAvailability(
  input: ModelSourceAvailabilityInput,
): ModelSourceAvailability {
  if (!input.enabled) {
    return 'disabled';
  }
  if (input.issueCount > 0) {
    return 'incomplete';
  }
  if (!input.hasModels) {
    // Enabled without models is not ready, but not a "draft incomplete" schema failure.
    return 'untested';
  }
  const status = input.testState?.status ?? 'idle';
  if (status === 'loading') {
    return 'testing';
  }
  if (status === 'error') {
    return 'unavailable';
  }
  if (status === 'success') {
    return 'available';
  }
  return 'untested';
}

/**
 * Sources that may appear in primary task-assignment short lists.
 * Untested/unavailable/incomplete never qualify as healthy assignable targets.
 * Existing configured values may still display as stale until retested.
 */
export function isModelSourceAssignable(availability: ModelSourceAvailability): boolean {
  return availability === 'available';
}

/** Connection names that failed a session connectivity test. */
export function collectFailedTestConnectionNames(
  channels: ReadonlyArray<{ id: string; name: string }>,
  testStates: Readonly<Record<string, { status?: string } | undefined>>,
): string[] {
  return channels
    .filter((channel) => testStates[channel.id]?.status === 'error')
    .map((channel) => channel.name)
    .filter(Boolean);
}

export function canEnableModelSource(options: {
  testState?: ChannelTestState | null;
  requireSuccessfulTest?: boolean;
}): boolean {
  const status = options.testState?.status ?? 'idle';
  if (status === 'error' || status === 'loading') {
    return false;
  }
  if (options.requireSuccessfulTest) {
    return status === 'success';
  }
  return true;
}
