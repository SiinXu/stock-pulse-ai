// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import {
  BEGINNER_MODE_STORAGE_KEY,
  SETTINGS_MODE_STORAGE_KEY,
  useBeginnerMode,
} from '../useBeginnerMode';

afterEach(() => {
  window.localStorage.clear();
});

describe('useBeginnerMode (Essentials/Expert)', () => {
  it('defaults to essentials when nothing is persisted', () => {
    const { result } = renderHook(() => useBeginnerMode());
    expect(result.current.mode).toBe('essentials');
    expect(result.current.beginnerMode).toBe(true);
  });

  it('persists Expert mode and reads it back on remount', () => {
    const { result } = renderHook(() => useBeginnerMode());
    act(() => result.current.setMode('expert'));
    expect(result.current.mode).toBe('expert');
    expect(result.current.beginnerMode).toBe(false);
    expect(window.localStorage.getItem(SETTINGS_MODE_STORAGE_KEY)).toBe('expert');
    expect(window.localStorage.getItem(BEGINNER_MODE_STORAGE_KEY)).toBe('0');

    const remount = renderHook(() => useBeginnerMode());
    expect(remount.result.current.mode).toBe('expert');
  });

  it('migrates legacy beginner-mode storage key', () => {
    window.localStorage.setItem(BEGINNER_MODE_STORAGE_KEY, '0');
    const { result } = renderHook(() => useBeginnerMode());
    expect(result.current.mode).toBe('expert');

    act(() => result.current.setBeginnerMode(true));
    expect(window.localStorage.getItem(SETTINGS_MODE_STORAGE_KEY)).toBe('essentials');
    expect(window.localStorage.getItem(BEGINNER_MODE_STORAGE_KEY)).toBe('1');
  });
});
