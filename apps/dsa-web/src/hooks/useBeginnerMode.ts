// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useState } from 'react';

// Client-only preference, mirroring the sidebar-collapse persistence pattern.
// Default is off (full/professional view) so existing users see no change until
// they opt in; beginner mode is additive progressive disclosure, not a gate.
export const BEGINNER_MODE_STORAGE_KEY = 'dsa-beginner-mode';

function readBeginnerMode(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  try {
    return window.localStorage.getItem(BEGINNER_MODE_STORAGE_KEY) === '1';
  } catch {
    // Private-mode / storage-disabled browsers fall back to the full view.
    return false;
  }
}

export interface UseBeginnerModeResult {
  beginnerMode: boolean;
  setBeginnerMode: (value: boolean) => void;
}

export function useBeginnerMode(): UseBeginnerModeResult {
  const [beginnerMode, setBeginnerModeState] = useState<boolean>(readBeginnerMode);

  const setBeginnerMode = useCallback((value: boolean) => {
    setBeginnerModeState(value);
    if (typeof window === 'undefined') {
      return;
    }
    try {
      window.localStorage.setItem(BEGINNER_MODE_STORAGE_KEY, value ? '1' : '0');
    } catch {
      // Persistence is best-effort; the in-memory value still drives the session.
    }
  }, []);

  return { beginnerMode, setBeginnerMode };
}
