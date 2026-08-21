// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { createDeferred } from '../../test-utils';
import {
  buildDecisionSignalListQueryKey,
  useDecisionSignalListQuery,
} from '../useDecisionSignalListQuery';

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

describe('useDecisionSignalListQuery', () => {
  it('cancels an in-flight list load when the query key changes', async () => {
    const firstLoad = createDeferred<void>();
    const loadSignals = vi.fn(() => firstLoad.promise);
    const onCancelInFlight = vi.fn();
    const firstKey = buildDecisionSignalListQueryKey({
      scope: 'all',
      page: 1,
      appliedFilters: { status: 'active' },
      watchlistLoading: false,
      watchlistCodes: [],
      watchlistErrorMessage: null,
    });
    const { rerender } = renderHook(
      ({ queryKey }) => useDecisionSignalListQuery({
        queryKey,
        loadSignals,
        onCancelInFlight,
      }),
      {
        wrapper: createWrapper(),
        initialProps: { queryKey: firstKey },
      },
    );

    await waitFor(() => expect(loadSignals).toHaveBeenCalledTimes(1));

    const secondKey = buildDecisionSignalListQueryKey({
      scope: 'all',
      page: 2,
      appliedFilters: { status: 'active' },
      watchlistLoading: false,
      watchlistCodes: [],
      watchlistErrorMessage: null,
    });
    rerender({ queryKey: secondKey });

    await waitFor(() => expect(onCancelInFlight).toHaveBeenCalled());
    await act(async () => {
      firstLoad.resolve();
      await firstLoad.promise;
    });
  });
});
