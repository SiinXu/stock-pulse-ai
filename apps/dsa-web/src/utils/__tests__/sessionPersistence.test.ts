// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it } from 'vitest';
import {
  CHAT_SESSION_STORAGE_KEY,
  DEEP_RESEARCH_SESSION_STORAGE_PREFIX,
  SCREEN_TASK_SESSION_STORAGE_KEY,
  WEB_SESSION_CONTINUITY_STORAGE_KEY,
  clearPersistedWebSession,
  readSessionItemWithLegacyLocal,
} from '../sessionPersistence';

describe('sessionPersistence', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('migrates legacy local values into tab-scoped session storage', () => {
    window.localStorage.setItem(CHAT_SESSION_STORAGE_KEY, 'session-legacy');

    expect(readSessionItemWithLegacyLocal(CHAT_SESSION_STORAGE_KEY)).toBe('session-legacy');
    expect(window.sessionStorage.getItem(CHAT_SESSION_STORAGE_KEY)).toBe('session-legacy');
    expect(window.localStorage.getItem(CHAT_SESSION_STORAGE_KEY)).toBeNull();
  });

  it('removes a duplicate legacy value when session storage is already authoritative', () => {
    window.sessionStorage.setItem(CHAT_SESSION_STORAGE_KEY, 'session-current');
    window.localStorage.setItem(CHAT_SESSION_STORAGE_KEY, 'session-legacy');

    expect(readSessionItemWithLegacyLocal(CHAT_SESSION_STORAGE_KEY)).toBe('session-current');
    expect(window.localStorage.getItem(CHAT_SESSION_STORAGE_KEY)).toBeNull();
  });

  it('clears session traces on logout without deleting durable UI preferences', () => {
    window.sessionStorage.setItem(WEB_SESSION_CONTINUITY_STORAGE_KEY, '{}');
    window.sessionStorage.setItem(CHAT_SESSION_STORAGE_KEY, 'session-current');
    window.sessionStorage.setItem(SCREEN_TASK_SESSION_STORAGE_KEY, '{}');
    window.sessionStorage.setItem(`${DEEP_RESEARCH_SESSION_STORAGE_PREFIX}current`, '{}');
    window.localStorage.setItem(CHAT_SESSION_STORAGE_KEY, 'session-legacy');
    window.localStorage.setItem(`${DEEP_RESEARCH_SESSION_STORAGE_PREFIX}legacy`, '{}');
    window.localStorage.setItem('dsa.uiLanguage', 'en');
    window.localStorage.setItem('stockpulse-theme', 'dark');

    clearPersistedWebSession();

    expect(window.sessionStorage.length).toBe(0);
    expect(window.localStorage.getItem(CHAT_SESSION_STORAGE_KEY)).toBeNull();
    expect(window.localStorage.getItem(`${DEEP_RESEARCH_SESSION_STORAGE_PREFIX}legacy`)).toBeNull();
    expect(window.localStorage.getItem('dsa.uiLanguage')).toBe('en');
    expect(window.localStorage.getItem('stockpulse-theme')).toBe('dark');
  });
});
