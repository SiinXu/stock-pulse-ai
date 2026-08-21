// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it } from 'vitest';
import {
  beginNotificationChannelTest,
  classifyNotificationTestOutcome,
  computeNotificationConfigurationFingerprint,
  getNotificationChannelTestRecord,
  isCurrentNotificationChannelTest,
  resetNotificationChannelTestStatusForTests,
  resolveNotificationChannelHealth,
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

  it('classifies an all-failed or success:false probe as failed, not verified', () => {
    expect(classifyNotificationTestOutcome({
      success: false,
      attempts: [],
    })).toBe('failed');
    expect(classifyNotificationTestOutcome({
      success: false,
      attempts: [
        { channel: 'feishu', success: false, message: 'missing webhook', stage: 'send', retryable: false },
      ],
    })).toBe('failed');
  });

  it('ignores a superseded same-channel probe commit so the newer attempt wins', () => {
    const first = beginNotificationChannelTest('feishu');
    const second = beginNotificationChannelTest('feishu');
    expect(isCurrentNotificationChannelTest('feishu', first)).toBe(false);
    expect(isCurrentNotificationChannelTest('feishu', second)).toBe(true);

    expect(setNotificationChannelTestRecord({
      channel: 'feishu',
      outcome: 'verified',
      message: 'stale success',
      attempts: [],
      configVersion: 'v1',
      configFingerprint: 'sha256:one',
      at: Date.now(),
    }, first)).toBe(false);
    expect(getNotificationChannelTestRecord('feishu')).toBeUndefined();

    expect(setNotificationChannelTestRecord({
      channel: 'feishu',
      outcome: 'failed',
      message: 'newer failure',
      attempts: [],
      configVersion: 'v1',
      configFingerprint: 'sha256:one',
      at: Date.now(),
    }, second)).toBe(true);
    expect(getNotificationChannelTestRecord('feishu')?.outcome).toBe('failed');

    expect(setNotificationChannelTestRecord({
      channel: 'feishu',
      outcome: 'verified',
      message: 'stale success arrived last',
      attempts: [],
      configVersion: 'v1',
      configFingerprint: 'sha256:one',
      at: Date.now(),
    }, first)).toBe(false);
    expect(getNotificationChannelTestRecord('feishu')?.outcome).toBe('failed');
    expect(getNotificationChannelTestRecord('feishu')?.message).toBe('newer failure');
  });

  it('keeps per-channel attempt identity isolated so another channel cannot supersede this one', () => {
    const feishuAttempt = beginNotificationChannelTest('feishu');
    const emailAttempt = beginNotificationChannelTest('email');
    expect(isCurrentNotificationChannelTest('feishu', feishuAttempt)).toBe(true);
    expect(isCurrentNotificationChannelTest('email', emailAttempt)).toBe(true);

    expect(setNotificationChannelTestRecord({
      channel: 'feishu',
      outcome: 'failed',
      message: 'feishu failed',
      attempts: [],
      configVersion: 'v1',
      configFingerprint: 'sha256:feishu',
      at: Date.now(),
    }, feishuAttempt)).toBe(true);
    expect(setNotificationChannelTestRecord({
      channel: 'email',
      outcome: 'verified',
      message: 'email ok',
      attempts: [],
      configVersion: 'v1',
      configFingerprint: 'sha256:email',
      at: Date.now(),
    }, emailAttempt)).toBe(true);

    expect(getNotificationChannelTestRecord('feishu')?.outcome).toBe('failed');
    expect(getNotificationChannelTestRecord('email')?.outcome).toBe('verified');
  });

  it('keeps failed and degraded ahead of draft so a probe failure is never hidden', () => {
    expect(resolveNotificationChannelHealth({
      configured: true,
      hasPendingConfiguration: true,
      lastTestOutcome: 'failed',
    })).toBe('failed');
    expect(resolveNotificationChannelHealth({
      configured: true,
      hasPendingConfiguration: true,
      lastTestOutcome: 'degraded',
    })).toBe('degraded');
    expect(resolveNotificationChannelHealth({
      configured: true,
      hasPendingConfiguration: true,
      lastTestOutcome: 'verified',
    })).toBe('draft');
    expect(resolveNotificationChannelHealth({
      configured: true,
      hasPendingConfiguration: false,
      lastTestOutcome: 'verified',
    })).toBe('verified');
    expect(resolveNotificationChannelHealth({
      configured: true,
      hasPendingConfiguration: false,
      lastTestOutcome: 'failed',
    })).toBe('failed');
    expect(resolveNotificationChannelHealth({
      configured: true,
      hasPendingConfiguration: true,
    })).toBe('needs_test');
    expect(resolveNotificationChannelHealth({
      configured: false,
      hasPendingConfiguration: true,
      lastTestOutcome: 'failed',
    })).toBe('unconfigured');
  });
});
