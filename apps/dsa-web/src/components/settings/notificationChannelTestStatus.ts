// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Session-scoped last notification-channel test results shared by the
 * Notifications hub cards and the standalone test panel. Not persisted;
 * a reload clears verification badges (config values remain the source of truth).
 */

export type NotificationChannelTestRecord = {
  /** Routing / test API channel value (e.g. custom, serverchan3). */
  channel: string;
  success: boolean;
  message: string;
  errorCode?: string | null;
  at: number;
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

export function getNotificationChannelTestStatusVersion(): number {
  return version;
}

export function getNotificationChannelTestRecord(
  channel: string,
): NotificationChannelTestRecord | undefined {
  return records.get(channel);
}

export function getAllNotificationChannelTestRecords(): ReadonlyMap<
  string,
  NotificationChannelTestRecord
> {
  return records;
}

export function setNotificationChannelTestRecord(
  record: NotificationChannelTestRecord,
): void {
  records.set(record.channel, record);
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
