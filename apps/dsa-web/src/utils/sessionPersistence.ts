// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export const WEB_SESSION_CONTINUITY_STORAGE_KEY = 'dsa.web.sessionContinuity.v1';
export const CHAT_SESSION_STORAGE_KEY = 'dsa_chat_session_id';
export const DEEP_RESEARCH_SESSION_STORAGE_PREFIX = 'dsa_research_run:';
export const SCREEN_TASK_SESSION_STORAGE_KEY = 'dsa.alphasift.activeScreenTask.v1';

function getStorage(kind: 'local' | 'session'): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return kind === 'session' ? window.sessionStorage : window.localStorage;
  } catch {
    return null;
  }
}

export function readSessionItem(key: string): string | null {
  try {
    return getStorage('session')?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

export function writeSessionItem(key: string, value: string): void {
  try {
    getStorage('session')?.setItem(key, value);
  } catch {
    // Session persistence is best-effort; in-memory and URL state still work.
  }
}

export function removeSessionItem(key: string): void {
  try {
    getStorage('session')?.removeItem(key);
  } catch {
    // Session cleanup is best-effort when browser storage is unavailable.
  }
}

export function readSessionItemWithLegacyLocal(key: string): string | null {
  const sessionValue = readSessionItem(key);
  const localStorage = getStorage('local');
  if (sessionValue !== null) {
    try {
      localStorage?.removeItem(key);
    } catch {
      // The session value is still authoritative when legacy cleanup is unavailable.
    }
    return sessionValue;
  }

  try {
    const legacyValue = localStorage?.getItem(key) ?? null;
    if (legacyValue !== null) {
      writeSessionItem(key, legacyValue);
      localStorage?.removeItem(key);
    }
    return legacyValue;
  } catch {
    return null;
  }
}

function removeKeys(storage: Storage | null, exactKeys: ReadonlySet<string>, prefixes: readonly string[]): void {
  if (!storage) return;
  try {
    const keys = Array.from({ length: storage.length }, (_, index) => storage.key(index))
      .filter((key): key is string => key !== null);
    for (const key of keys) {
      if (exactKeys.has(key) || prefixes.some((prefix) => key.startsWith(prefix))) {
        storage.removeItem(key);
      }
    }
  } catch {
    // A disabled storage area must not prevent logout from completing.
  }
}

export function clearPersistedWebSession(): void {
  const exactKeys = new Set([
    WEB_SESSION_CONTINUITY_STORAGE_KEY,
    CHAT_SESSION_STORAGE_KEY,
    SCREEN_TASK_SESSION_STORAGE_KEY,
  ]);
  const prefixes = [DEEP_RESEARCH_SESSION_STORAGE_PREFIX];

  removeKeys(getStorage('session'), exactKeys, prefixes);
  // Remove traces written by versions that persisted Chat and Deep Research in localStorage.
  removeKeys(getStorage('local'), exactKeys, prefixes);
}
