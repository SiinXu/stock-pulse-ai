// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it } from 'vitest';
import {
  classifyNotificationTestOutcome,
  computeNotificationConfigurationFingerprint,
  getNotificationChannelTestRecord,
  resetNotificationChannelTestStatusForTests,
  setNotificationChannelTestRecord,
} from '../notificationChannelTestStatus';

describe('notificationChannelTestStatus', () => {
  beforeEach(() => resetNotificationChannelTestStatusForTests());

  it('binds evidence to a secret-safe canonical configuration and version', async () => {
    const first = await computeNotificationConfigurationFingerprint('feishu', 'v1', [
      { key: 'FEISHU_WEBHOOK_URL', value: 'https://example.com/secret' },
      { key: 'FEISHU_DOMAIN', value: 'feishu' },
    ]);
    const reordered = await computeNotificationConfigurationFingerprint('feishu', 'v1', [
      { key: 'FEISHU_DOMAIN', value: 'feishu' },
      { key: 'FEISHU_WEBHOOK_URL', value: 'https://example.com/secret' },
    ]);
    const edited = await computeNotificationConfigurationFingerprint('feishu', 'v1', [
      { key: 'FEISHU_DOMAIN', value: 'feishu' },
      { key: 'FEISHU_WEBHOOK_URL', value: 'https://example.com/changed' },
    ]);
    const refreshed = await computeNotificationConfigurationFingerprint('feishu', 'v2', [
      { key: 'FEISHU_DOMAIN', value: 'feishu' },
      { key: 'FEISHU_WEBHOOK_URL', value: 'https://example.com/secret' },
    ]);

    expect(first).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(first).toBe(reordered);
    expect(first).not.toContain('secret');
    expect(edited).not.toBe(first);
    expect(refreshed).not.toBe(first);
  });

  it('rejects stale, mismatched, and expired evidence', () => {
    setNotificationChannelTestRecord({
      channel: 'feishu',
      outcome: 'verified',
      message: 'ok',
      attempts: [],
      configVersion: 'v1',
      configFingerprint: 'sha256:one',
      at: 1_000,
      expiresAt: 2_000,
    });

    expect(getNotificationChannelTestRecord('feishu', {
      configVersion: 'v1',
      configFingerprint: 'sha256:one',
    }, 1_500)?.outcome).toBe('verified');
    expect(getNotificationChannelTestRecord('feishu', {
      configVersion: 'v2',
      configFingerprint: 'sha256:one',
    }, 1_500)).toBeUndefined();
    expect(getNotificationChannelTestRecord('feishu', {
      configVersion: 'v1',
      configFingerprint: 'sha256:changed',
    }, 1_500)).toBeUndefined();
    expect(getNotificationChannelTestRecord('feishu', undefined, 2_000)).toBeUndefined();
  });

  it('never promotes partial multi-target delivery to verified', () => {
    expect(classifyNotificationTestOutcome({
      success: true,
      attempts: [
        { channel: 'custom', success: true, message: 'ok', stage: 'send', retryable: false },
        { channel: 'custom', success: false, message: 'failed', stage: 'send', retryable: true },
      ],
    })).toBe('degraded');
  });
});
