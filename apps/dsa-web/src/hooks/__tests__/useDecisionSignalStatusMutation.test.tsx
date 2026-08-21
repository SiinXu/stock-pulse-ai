// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { createDeferred } from '../../test-utils';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import { useDecisionSignalStatusMutation } from '../useDecisionSignalStatusMutation';

vi.mock('../../api/decisionSignals', () => ({
  decisionSignalsApi: {
    updateStatus: vi.fn(),
  },
}));

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

const signal: DecisionSignalItem = {
  id: 7,
  stockCode: '600519',
  stockName: '贵州茅台',
  market: 'cn',
  sourceType: 'analysis',
  triggerSource: 'web',
  action: 'hold',
  confidence: 0.8,
  planQuality: 'complete',
  status: 'active',
  createdAt: '2026-08-21T00:00:00Z',
  updatedAt: '2026-08-21T00:00:00Z',
};

describe('useDecisionSignalStatusMutation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('ignores a second confirmation while the first write is in flight', async () => {
    const deferred = createDeferred<DecisionSignalItem>();
    vi.mocked(decisionSignalsApi.updateStatus).mockReturnValueOnce(deferred.promise);
    const { result } = renderHook(
      () => useDecisionSignalStatusMutation({ isMounted: () => true }),
      { wrapper: createWrapper() },
    );

    let first: Promise<unknown> | undefined;
    let second: Promise<unknown> | undefined;
    await act(async () => {
      first = result.current.runStatusUpdate({ signalId: 7, status: 'invalidated' });
      second = result.current.runStatusUpdate({ signalId: 7, status: 'closed' });
    });

    expect(decisionSignalsApi.updateStatus).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(result.current.isUpdating).toBe(true));

    await act(async () => {
      deferred.resolve({ ...signal, status: 'invalidated' });
      await deferred.promise;
    });

    await expect(first).resolves.toEqual({
      kind: 'ok',
      item: { ...signal, status: 'invalidated' },
    });
    await expect(second).resolves.toEqual({ kind: 'ignored' });
    expect(result.current.isUpdating).toBe(true);

    let third: Promise<unknown> | undefined;
    await act(async () => {
      third = result.current.runStatusUpdate({ signalId: 7, status: 'archived' });
    });
    await expect(third).resolves.toEqual({ kind: 'ignored' });
    expect(decisionSignalsApi.updateStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      result.current.releaseStatusUpdate();
    });
    await waitFor(() => expect(result.current.isUpdating).toBe(false));
  });

  it('returns a parsed error and does not retry', async () => {
    vi.mocked(decisionSignalsApi.updateStatus).mockRejectedValueOnce(new Error('status update failed'));
    const { result } = renderHook(
      () => useDecisionSignalStatusMutation({ isMounted: () => true }),
      { wrapper: createWrapper() },
    );

    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.runStatusUpdate({ signalId: 7, status: 'invalidated' });
    });

    expect(decisionSignalsApi.updateStatus).toHaveBeenCalledTimes(1);
    expect(outcome).toEqual({
      kind: 'error',
      error: expect.objectContaining({
        title: '请求失败',
        message: '请求未能完成，请稍后重试。',
      }),
    });
    expect((outcome as { error: { message: string } }).error.message).not.toBe('status update failed');
    expect(result.current.isUpdating).toBe(false);
  });

  it('does not apply success after unmount', async () => {
    const deferred = createDeferred<DecisionSignalItem>();
    vi.mocked(decisionSignalsApi.updateStatus).mockReturnValueOnce(deferred.promise);
    let mounted = true;
    const { result, unmount } = renderHook(
      () => useDecisionSignalStatusMutation({ isMounted: () => mounted }),
      { wrapper: createWrapper() },
    );

    let pending: Promise<unknown> | undefined;
    await act(async () => {
      pending = result.current.runStatusUpdate({ signalId: 7, status: 'invalidated' });
    });
    mounted = false;
    unmount();
    await act(async () => {
      deferred.resolve({ ...signal, status: 'invalidated' });
      await deferred.promise;
    });
    await expect(pending).resolves.toEqual({ kind: 'unmounted' });
  });
});
