// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { createDeferred } from '../../test-utils';
import { useDecisionSignalDetailQueries } from '../useDecisionSignalDetailQueries';

vi.mock('../../api/decisionSignals', () => ({
  decisionSignalsApi: {
    getSignalOutcomes: vi.fn(),
    getFeedback: vi.fn(),
  },
}));

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe('useDecisionSignalDetailQueries', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not fetch detail until a signal is selected', () => {
    const { result } = renderHook(
      () => useDecisionSignalDetailQueries(null),
      { wrapper: createWrapper() },
    );
    expect(decisionSignalsApi.getSignalOutcomes).not.toHaveBeenCalled();
    expect(decisionSignalsApi.getFeedback).not.toHaveBeenCalled();
    expect(result.current.selectedOutcomesLoading).toBe(false);
    expect(result.current.selectedFeedback).toBeNull();
  });

  it('drops a stale detail response when selection changes', async () => {
    const firstOutcomes = createDeferred<{ items: Array<{ id: number }> }>();
    vi.mocked(decisionSignalsApi.getSignalOutcomes)
      .mockReturnValueOnce(firstOutcomes.promise as never)
      .mockResolvedValueOnce({ items: [{ id: 2 }] } as never);
    vi.mocked(decisionSignalsApi.getFeedback).mockResolvedValue(null as never);

    const { result, rerender } = renderHook(
      ({ signalId }: { signalId: number | null }) => useDecisionSignalDetailQueries(signalId),
      { wrapper: createWrapper(), initialProps: { signalId: 1 } },
    );

    await waitFor(() => expect(decisionSignalsApi.getSignalOutcomes).toHaveBeenCalledWith(1));
    rerender({ signalId: 2 });
    await waitFor(() => expect(decisionSignalsApi.getSignalOutcomes).toHaveBeenCalledWith(2));

    firstOutcomes.resolve({ items: [{ id: 1 }] });
    await waitFor(() => expect(result.current.selectedOutcomes).toEqual([{ id: 2 }]));
    expect(result.current.selectedOutcomes).not.toEqual([{ id: 1 }]);
  });
});
