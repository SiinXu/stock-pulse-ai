// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, it } from 'vitest';
import {
  DEFAULT_ALERT_COOLDOWN_SECONDS,
  getEffectiveAlertCooldown,
  MAX_ALERT_COOLDOWN_SECONDS,
} from '../alertCooldown';

describe('getEffectiveAlertCooldown', () => {
  it('uses the backend default only when the known key is absent', () => {
    expect(getEffectiveAlertCooldown({ server_owned_mode: 'rolling' })).toEqual({
      mode: 'default',
      seconds: DEFAULT_ALERT_COOLDOWN_SECONDS,
    });
  });

  it('matches worker normalization for booleans and invalid values', () => {
    expect(getEffectiveAlertCooldown({ cooldown_seconds: true })).toEqual({
      mode: 'custom',
      seconds: 1,
    });
    expect(getEffectiveAlertCooldown({ cooldown_seconds: false })).toEqual({
      mode: 'disabled',
      seconds: 0,
    });
    expect(getEffectiveAlertCooldown({ cooldown_seconds: 'invalid' })).toEqual({
      mode: 'disabled',
      seconds: 0,
    });
  });

  it('caps stored values at the worker-supported maximum', () => {
    expect(getEffectiveAlertCooldown({
      cooldown_seconds: Number.MAX_SAFE_INTEGER,
    })).toEqual({
      mode: 'custom',
      seconds: MAX_ALERT_COOLDOWN_SECONDS,
    });
  });
});
