// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useState } from 'react';

/**
 * Settings progressive-disclosure preference.
 * - essentials: curated BEGINNER_ESSENTIAL_SECTION_IDS (+ active deep-linked section)
 * - expert: full Settings tree (default-off advanced capability flags stay visible here)
 *
 * Legacy key `dsa-beginner-mode` (`1`/`0`) is migrated once into `dsa-settings-mode`.
 * Default when nothing is stored: essentials (issue #797 progressive disclosure).
 */
export const BEGINNER_MODE_STORAGE_KEY = 'dsa-beginner-mode';
export const SETTINGS_MODE_STORAGE_KEY = 'dsa-settings-mode';

export type SettingsDisplayMode = 'essentials' | 'expert';

function readSettingsMode(): SettingsDisplayMode {
  if (typeof window === 'undefined') {
    return 'essentials';
  }
  try {
    const stored = window.localStorage.getItem(SETTINGS_MODE_STORAGE_KEY);
    if (stored === 'essentials' || stored === 'expert') {
      return stored;
    }
    const legacy = window.localStorage.getItem(BEGINNER_MODE_STORAGE_KEY);
    if (legacy === '1') return 'essentials';
    if (legacy === '0') return 'expert';
  } catch {
    // Private-mode / storage-disabled browsers fall back to essentials.
  }
  return 'essentials';
}

export interface UseBeginnerModeResult {
  /** True when Essentials mode is active (hides non-essential nav sections). */
  beginnerMode: boolean;
  mode: SettingsDisplayMode;
  setBeginnerMode: (value: boolean) => void;
  setMode: (mode: SettingsDisplayMode) => void;
}

function persistMode(mode: SettingsDisplayMode): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(SETTINGS_MODE_STORAGE_KEY, mode);
    window.localStorage.setItem(BEGINNER_MODE_STORAGE_KEY, mode === 'essentials' ? '1' : '0');
  } catch {
    // Persistence is best-effort; the in-memory value still drives the session.
  }
}

export function useBeginnerMode(): UseBeginnerModeResult {
  const [mode, setModeState] = useState<SettingsDisplayMode>(readSettingsMode);

  const setMode = useCallback((next: SettingsDisplayMode) => {
    setModeState(next);
    persistMode(next);
  }, []);

  const setBeginnerMode = useCallback((value: boolean) => {
    setMode(value ? 'essentials' : 'expert');
  }, [setMode]);

  return {
    beginnerMode: mode === 'essentials',
    mode,
    setBeginnerMode,
    setMode,
  };
}
