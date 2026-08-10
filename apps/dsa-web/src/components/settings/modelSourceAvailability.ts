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

export function isModelSourceAssignable(availability: ModelSourceAvailability): boolean {
  return availability === 'available' || availability === 'untested';
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
