// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  assertPortfolioResponseContext,
  PortfolioResponseContextError,
  useContextBoundPortfolioRequest,
} from '../useContextBoundPortfolioRequest';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('useContextBoundPortfolioRequest', () => {
  it('clears results and ignores a late response after context changes', async () => {
    const first = deferred<string>();
    const { result, rerender } = renderHook(
      ({ contextKey }) => useContextBoundPortfolioRequest<string>(contextKey),
      { initialProps: { contextKey: 'account-1:fifo' } },
    );

    act(() => {
      void result.current.execute(() => first.promise);
    });
    expect(result.current.isRunning).toBe(true);

    rerender({ contextKey: 'account-2:avg' });
    expect(result.current.result).toBeNull();
    expect(result.current.isRunning).toBe(false);

    await act(async () => {
      first.resolve('stale result');
      await first.promise;
    });
    expect(result.current.result).toBeNull();
    expect(result.current.hasCompleted).toBe(false);
  });

  it('keeps a result started immediately after the context key first becomes runnable', async () => {
    const { result, rerender } = renderHook(
      ({ contextKey }) => useContextBoundPortfolioRequest<string>(contextKey),
      { initialProps: { contextKey: 'scenario:' } },
    );

    rerender({ contextKey: 'scenario:market_down_10' });

    await act(async () => {
      await result.current.execute(async () => 'fresh result');
    });

    expect(result.current.result).toBe('fresh result');
    expect(result.current.hasCompleted).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it('blocks duplicate pending execution for the same context', async () => {
    const pending = deferred<string>();
    const request = vi.fn(() => pending.promise);
    const { result } = renderHook(() => useContextBoundPortfolioRequest<string>('account-1:fifo'));

    act(() => {
      void result.current.execute(request);
      void result.current.execute(request);
    });
    expect(request).toHaveBeenCalledTimes(1);

    await act(async () => {
      pending.resolve('accepted');
      await pending.promise;
    });
    expect(result.current.result).toBe('accepted');
    expect(result.current.hasCompleted).toBe(true);
  });

  it('surfaces response account and cost-method mismatches', async () => {
    const response = { accountId: 2, costMethod: 'avg' as const };
    const { result } = renderHook(() => (
      useContextBoundPortfolioRequest<typeof response>('account-1:fifo')
    ));

    await act(async () => {
      await result.current.execute(
        async () => response,
        (value) => assertPortfolioResponseContext(value, { accountId: 1, costMethod: 'fifo' }),
      );
    });

    expect(result.current.result).toBeNull();
    expect(result.current.error).toBeInstanceOf(PortfolioResponseContextError);
  });
});
