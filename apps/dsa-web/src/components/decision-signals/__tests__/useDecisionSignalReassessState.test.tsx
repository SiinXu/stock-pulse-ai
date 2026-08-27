// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  shouldAcceptReassessIdentityChange,
  useDecisionSignalReassessState,
  type ReassessLockedContext,
} from '../useDecisionSignalReassessState';

const locked: ReassessLockedContext = {
  signalId: 7,
  stockCode: '600519',
  sourceReportId: 3001,
};

describe('useDecisionSignalReassessState', () => {
  it('starts idle and unlocks identity changes', () => {
    const { result } = renderHook(() => useDecisionSignalReassessState());

    expect(result.current.sessionStatus).toBe('idle');
    expect(result.current.lockedContext).toBeNull();
    expect(result.current.shouldAcceptIdentityChange({ signalId: 8, stockCode: 'AAPL' })).toBe(true);
  });

  it('enters an active session, locks identity, and ignores a second enter', () => {
    const { result } = renderHook(() => useDecisionSignalReassessState());

    act(() => result.current.enterSession(locked));
    expect(result.current.sessionStatus).toBe('active');
    expect(result.current.lockedContext).toEqual(locked);
    expect(result.current.shouldAcceptIdentityChange({ signalId: 7, stockCode: '600519' })).toBe(true);
    expect(result.current.shouldAcceptIdentityChange({ signalId: 8 })).toBe(false);
    expect(result.current.shouldAcceptIdentityChange({ stockCode: 'AAPL' })).toBe(false);

    act(() => result.current.enterSession({
      signalId: 8,
      stockCode: 'AAPL',
      sourceReportId: 3002,
    }));
    expect(result.current.lockedContext).toEqual(locked);
  });

  it('keeps the locked identity when list, latest, and timeline candidates change', () => {
    const { result } = renderHook(() => useDecisionSignalReassessState());

    act(() => result.current.enterSession(locked));
    // Candidate identity is not a hook input; replacing list/latest/timeline
    // groups cannot unlock the session-owned stock/signal context.
    expect(result.current.sessionStatus).toBe('active');
    expect(result.current.lockedContext).toEqual(locked);
    expect(shouldAcceptReassessIdentityChange(
      result.current.sessionStatus,
      result.current.lockedContext,
      { signalId: 8, stockCode: 'AAPL' },
    )).toBe(false);
    expect(shouldAcceptReassessIdentityChange(
      result.current.sessionStatus,
      result.current.lockedContext,
      { signalId: 9, stockCode: 'AAPL' },
    )).toBe(false);
    expect(shouldAcceptReassessIdentityChange(
      result.current.sessionStatus,
      result.current.lockedContext,
      { signalId: 10, stockCode: '000001' },
    )).toBe(false);
  });

  it('exits the session, clears preview state, and unlocks identity', () => {
    const { result } = renderHook(() => useDecisionSignalReassessState());

    act(() => result.current.enterSession(locked));
    act(() => result.current.dispatch({
      type: 'previewSuccess',
      response: {
        preview: null,
        item: null,
        created: false,
        persistStatus: null,
        warnings: [],
        blockedReason: null,
      },
    }));
    expect(result.current.response).not.toBeNull();

    act(() => result.current.exitSession());
    expect(result.current.sessionStatus).toBe('idle');
    expect(result.current.lockedContext).toBeNull();
    expect(result.current.response).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.persisting).toBe(false);
    expect(result.current.shouldAcceptIdentityChange({ signalId: 8, stockCode: 'AAPL' })).toBe(true);
  });
});
