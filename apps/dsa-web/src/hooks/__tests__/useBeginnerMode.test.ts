// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { BEGINNER_MODE_STORAGE_KEY, useBeginnerMode } from '../useBeginnerMode';

afterEach(() => {
  window.localStorage.clear();
});

describe('useBeginnerMode', () => {
  it('defaults to the full (professional) view when nothing is persisted', () => {
    const { result } = renderHook(() => useBeginnerMode());
    expect(result.current.beginnerMode).toBe(false);
  });

  it('persists the preference and reads it back on a fresh mount', () => {
    const { result } = renderHook(() => useBeginnerMode());
    act(() => result.current.setBeginnerMode(true));
    expect(result.current.beginnerMode).toBe(true);
    expect(window.localStorage.getItem(BEGINNER_MODE_STORAGE_KEY)).toBe('1');

    const remount = renderHook(() => useBeginnerMode());
    expect(remount.result.current.beginnerMode).toBe(true);
  });

  it('reads an existing stored preference on first mount', () => {
    window.localStorage.setItem(BEGINNER_MODE_STORAGE_KEY, '1');
    const { result } = renderHook(() => useBeginnerMode());
    expect(result.current.beginnerMode).toBe(true);
    act(() => result.current.setBeginnerMode(false));
    expect(window.localStorage.getItem(BEGINNER_MODE_STORAGE_KEY)).toBe('0');
  });
});
