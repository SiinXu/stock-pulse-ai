// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type {
  NotificationTestAttempt,
  SystemConfigUpdateItem,
  TestNotificationChannelResponse,
} from '../../types/systemConfig';

/** Session evidence expires so an old connectivity probe is never durable health. */
export const NOTIFICATION_TEST_EVIDENCE_TTL_MS = 30 * 60 * 1000;

export type NotificationChannelTestOutcome = 'verified' | 'degraded' | 'failed';

export type NotificationConfigurationIdentity = {
  configVersion: string;
  configFingerprint: string;
};

export type NotificationChannelTestRecord = NotificationConfigurationIdentity & {
  /** Routing / test API channel value (e.g. custom, serverchan3). */
  channel: string;
  outcome: NotificationChannelTestOutcome;
  message: string;
  errorCode?: string | null;
  attempts: NotificationTestAttempt[];
  at: number;
  expiresAt: number;
};

type Listener = () => void;

const records = new Map<string, NotificationChannelTestRecord>();
const listeners = new Set<Listener>();
/** Monotonic version so React useSyncExternalStore can detect updates. */
let version = 0;

function emit(): void {
  version += 1;
  for (const listener of listeners) {
    listener();
  }
}

function canonicalConfiguration(
  channel: string,
  configVersion: string,
  items: readonly SystemConfigUpdateItem[],
): string {
  const normalizedItems = items
    .map((item) => ({ key: item.key.trim().toUpperCase(), value: String(item.value ?? '') }))
    .sort((left, right) => left.key.localeCompare(right.key));
  return JSON.stringify({ channel, configVersion, items: normalizedItems });
}

/**
 * Return a one-way identity for the exact tested values without retaining raw
 * webhooks, tokens, or recipients in the shared evidence store.
 */
export async function computeNotificationConfigurationFingerprint(
  channel: string,
  configVersion: string,
  items: readonly SystemConfigUpdateItem[],
): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error('notification_configuration_fingerprint_unavailable');
  }
  const bytes = new TextEncoder().encode(canonicalConfiguration(channel, configVersion, items));
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  const hex = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
  return `sha256:${hex}`;
}

export function classifyNotificationTestOutcome(
  response: Pick<TestNotificationChannelResponse, 'success' | 'attempts'>,
): NotificationChannelTestOutcome {
  if (!response.attempts.length) {
    return response.success ? 'verified' : 'failed';
  }
  const successCount = response.attempts.filter((attempt) => attempt.success).length;
  if (successCount === response.attempts.length) return 'verified';
  if (successCount > 0) return 'degraded';
  return 'failed';
}

export function getNotificationChannelTestStatusVersion(): number {
  return version;
}

export function getNotificationChannelTestRecord(
  channel: string,
  identity?: NotificationConfigurationIdentity,
  now = Date.now(),
): NotificationChannelTestRecord | undefined {
  const record = records.get(channel);
  if (!record || record.expiresAt <= now) return undefined;
  if (
    identity
    && (
      record.configVersion !== identity.configVersion
      || record.configFingerprint !== identity.configFingerprint
    )
  ) {
    return undefined;
  }
  return record;
}

export function getAllNotificationChannelTestRecords(): ReadonlyMap<
  string,
  NotificationChannelTestRecord
> {
  return records;
}

export function setNotificationChannelTestRecord(
  record: Omit<NotificationChannelTestRecord, 'expiresAt'> & { expiresAt?: number },
): void {
  records.set(record.channel, {
    ...record,
    expiresAt: record.expiresAt ?? record.at + NOTIFICATION_TEST_EVIDENCE_TTL_MS,
  });
  emit();
}

export function clearNotificationChannelTestRecord(channel: string): void {
  if (records.delete(channel)) emit();
}

export function clearNotificationChannelTestRecords(): void {
  if (!records.size) return;
  records.clear();
  emit();
}

export function subscribeNotificationChannelTestStatus(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Test-only reset so specs do not leak status across cases. */
export function resetNotificationChannelTestStatusForTests(): void {
  records.clear();
  emit();
}
