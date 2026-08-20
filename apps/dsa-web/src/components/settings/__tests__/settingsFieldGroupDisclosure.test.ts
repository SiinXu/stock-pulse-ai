// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it, vi } from 'vitest';
import {
  SETTINGS_DEFAULT_OPEN_GROUP_IDS,
  focusSettingsFieldWhenPresent,
  isSettingsGroupDefaultOpen,
  parseSettingsFieldHash,
  resolveSettingsRevealFieldKey,
  settingsRevealUrlFingerprint,
} from '../settingsFieldGroupDisclosure';

describe('settingsFieldGroupDisclosure', () => {
  it('defaults open only quote, primary, and schedule', () => {
    expect([...SETTINGS_DEFAULT_OPEN_GROUP_IDS]).toEqual(['quote', 'primary', 'schedule']);
    expect(isSettingsGroupDefaultOpen('quote')).toBe(true);
    expect(isSettingsGroupDefaultOpen('primary')).toBe(true);
    expect(isSettingsGroupDefaultOpen('schedule')).toBe(true);
    for (const groupId of ['search', 'news', 'other', 'routing', 'report', 'behavior', 'web', 'log']) {
      expect(isSettingsGroupDefaultOpen(groupId), groupId).toBe(false);
    }
  });

  it('parses a field hash and prefers an explicit reveal request', () => {
    expect(parseSettingsFieldHash('#setting-WEBUI_PORT')).toBe('WEBUI_PORT');
    expect(parseSettingsFieldHash('#other')).toBeNull();
    expect(resolveSettingsRevealFieldKey({
      requestKey: 'TAVILY_API_KEYS',
      queryField: 'WEBUI_PORT',
      hash: '#setting-LOG_LEVEL',
    })).toBe('TAVILY_API_KEYS');
    expect(resolveSettingsRevealFieldKey({
      queryField: 'WEBUI_PORT',
      hash: '#setting-LOG_LEVEL',
    })).toBe('WEBUI_PORT');
    expect(resolveSettingsRevealFieldKey({
      hash: '#setting-LOG_LEVEL',
    })).toBe('LOG_LEVEL');
  });

  it('lets a later query or hash win after the request URL fingerprint changes', () => {
    const requestUrlFingerprint = settingsRevealUrlFingerprint(null, '');
    expect(resolveSettingsRevealFieldKey({
      requestKey: 'TAVILY_API_KEYS',
      requestUrlFingerprint,
      queryField: 'WEBUI_PORT',
      hash: '',
    })).toBe('WEBUI_PORT');
    expect(resolveSettingsRevealFieldKey({
      requestKey: 'TAVILY_API_KEYS',
      requestUrlFingerprint,
      hash: '#setting-LOG_LEVEL',
    })).toBe('LOG_LEVEL');
    expect(resolveSettingsRevealFieldKey({
      requestKey: 'TAVILY_API_KEYS',
      requestUrlFingerprint,
      queryField: null,
      hash: '',
    })).toBe('TAVILY_API_KEYS');
  });

  it('retries focus until the field control is present and not inert', async () => {
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => (
      window.setTimeout(() => callback(0), 0) as unknown as number
    ));
    vi.stubGlobal('cancelAnimationFrame', (id: number) => {
      window.clearTimeout(id);
    });

    const cancel = focusSettingsFieldWhenPresent('WEBUI_PORT', { maxFrames: 20 });
    const host = document.createElement('div');
    host.setAttribute('inert', '');
    const blocked = document.createElement('input');
    blocked.id = 'setting-WEBUI_PORT';
    host.appendChild(blocked);
    document.body.appendChild(host);

    await vi.waitFor(() => {
      expect(document.getElementById('setting-WEBUI_PORT')).toBe(blocked);
    });
    expect(document.activeElement).not.toBe(blocked);

    const focus = vi.spyOn(blocked, 'focus');
    host.removeAttribute('inert');
    await vi.waitFor(() => {
      expect(focus).toHaveBeenCalled();
    });
    cancel();
    host.remove();
    vi.unstubAllGlobals();
  });
});
