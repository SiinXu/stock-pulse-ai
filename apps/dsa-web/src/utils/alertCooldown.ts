// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { AlertCooldownPolicy } from '../types/alerts';

export const ALERT_COOLDOWN_SECONDS_KEY = 'cooldown_seconds';
export const DEFAULT_ALERT_COOLDOWN_SECONDS = 24 * 60 * 60;
export const MAX_ALERT_COOLDOWN_SECONDS = 365 * 24 * 60 * 60;

export type AlertCooldownSelection = {
  mode: 'default' | 'disabled' | 'custom';
  seconds: number;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Mirrors the worker contract: a missing key uses 24 hours, zero disables the
 * cooldown, positive values are truncated to whole seconds, and invalid or
 * negative stored values execute as zero. The worker caps persisted policies
 * at one year so its datetime update always remains bounded.
 */
export function getEffectiveAlertCooldown(
  policy: AlertCooldownPolicy | null | undefined,
): AlertCooldownSelection {
  if (!isRecord(policy) || !Object.hasOwn(policy, ALERT_COOLDOWN_SECONDS_KEY)) {
    return { mode: 'default', seconds: DEFAULT_ALERT_COOLDOWN_SECONDS };
  }
  const rawValue = policy[ALERT_COOLDOWN_SECONDS_KEY];
  const parsed = typeof rawValue === 'boolean'
    ? Number(rawValue)
    : typeof rawValue === 'number'
      ? Math.trunc(rawValue)
      : typeof rawValue === 'string' && /^[+-]?\d+$/.test(rawValue.trim())
        ? Number(rawValue)
        : 0;
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return { mode: 'disabled', seconds: 0 };
  }
  return {
    mode: 'custom',
    seconds: Math.min(parsed, MAX_ALERT_COOLDOWN_SECONDS),
  };
}
