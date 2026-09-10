// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { systemConfigApi } from '../../api/systemConfig';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { GenerationBackendStatusResponse } from '../../types/systemConfig';
import {
  GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY,
  GENERATION_BACKEND_STATUS_CANCEL,
  GENERATION_BACKEND_STATUS_PREVIEW_DEBOUNCE_MS,
  GENERATION_BACKEND_STATUS_QUERY_SCHEDULE,
  buildGenerationBackendPreviewStatusQueryKey,
  buildGenerationBackendStatusQueryKey,
  fetchGenerationBackendStatus,
  useGenerationBackendStatusQuery,
} from '../useGenerationBackendStatusQuery';

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getGenerationBackendStatus: vi.fn(),
    previewGenerationBackendStatus: vi.fn(),
    testGenerationBackend: vi.fn(),
  },
}));

const getGenerationBackendStatus = vi.mocked(systemConfigApi.getGenerationBackendStatus);
const previewGenerationBackendStatus = vi.mocked(systemConfigApi.previewGenerationBackendStatus);
const testGenerationBackend = vi.mocked(systemConfigApi.testGenerationBackend);

function statusFor(backendId: string): GenerationBackendStatusResponse {
  return {
    primaryBackendId: backendId,
    fallbackBackendId: null,
    primary: {
      backendId,
      backendType: backendId === 'litellm' ? 'litellm' : 'local_cli',
      providerId: backendId,
      available: true,
      healthStatus: 'passed',
      supportsJson: true,
      supportsTools: backendId === 'litellm',
      supportsStream: true,
      supportsVision: false,
      isPrimary: true,
      fallbackTarget: null,
      maxConcurrency: 1,
      usageAvailable: backendId === 'litellm',
      lastErrorCode: null,
      lastErrorMessage: null,
    },
    fallback: null,
    backends: [],
  };
}

function serverError(): Error {
  return Object.assign(new Error('server'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'generation backend unavailable' },
    },
  });
}

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? createAppQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return { client: queryClient, wrapper: Wrapper };
}

function queryOptions(
  client: QueryClient,
  queryKey: readonly unknown[] = GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactGenerationBackendOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'generation-backend' && key.length === 1).toBe(false);
    expect(key[0] === 'local-models').toBe(false);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'config-presets').toBe(false);
    expect(key[0] === 'investment-framework').toBe(false);
    expect(key[0] === 'scheduled-tasks').toBe(false);
    expect(key[0] === 'scheduler').toBe(false);
    expect(key[0] === 'plugins').toBe(false);
    expect(key[0] === 'watchlist').toBe(false);
    expect(key[0] === 'scorecard').toBe(false);
    expect(key[0] === 'kronos').toBe(false);
    expect(key[0] === 'data-providers').toBe(false);
    expect(key[0] === 'outbound-activity').toBe(false);
    expect(key[0] === 'security-audit').toBe(false);
    expect(key[0] === 'capabilities').toBe(false);
    expect(key[0] === 'agent-models').toBe(false);
    expect(key[0] === 'home').toBe(false);
    if (key[0] === 'generation-backend') {
      expect(filters?.exact).toBe(true);
      expect(key[1]).toBe('status');
      expect(key[2] === 'saved' || key[2] === 'preview').toBe(true);
      if (key[2] === 'saved') {
        expect([...key]).toEqual(['generation-backend', 'status', 'saved']);
        expect(key).toHaveLength(3);
      } else {
        expect(key).toHaveLength(5);
        expect(key[0]).toBe('generation-backend');
        expect(key[1]).toBe('status');
        expect(key[2]).toBe('preview');
      }
    }
  }
}

async function flushQueryMicrotasks(rounds = 2) {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
  }
}

const DRAFT_ITEMS: Array<{ key: string; value: string }> = [
  { key: 'GENERATION_BACKEND', value: 'opencode_cli' },
];
const DRAFT_FINGERPRINT = JSON.stringify(DRAFT_ITEMS);

type StatusHookProps = {
  items: readonly { key: string; value: string }[];
  maskToken: string;
};

describe('useGenerationBackendStatusQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    getGenerationBackendStatus.mockResolvedValue(statusFor('codex_cli'));
    previewGenerationBackendStatus.mockResolvedValue(statusFor('opencode_cli'));
    testGenerationBackend.mockResolvedValue({
      success: true,
      mode: 'json',
      message: 'ok',
      status: statusFor('codex_cli').primary,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    onlineManager.setOnline(true);
    focusManager.setFocused(true);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
  });

  it('pins the exact saved/preview keys, schedule, and transport with no AbortSignal', async () => {
    expect([...GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY]).toEqual(['generation-backend', 'status', 'saved']);
    expect(GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY).toHaveLength(3);
    expect([...buildGenerationBackendPreviewStatusQueryKey(DRAFT_FINGERPRINT, '******')]).toEqual([
      'generation-backend',
      'status',
      'preview',
      DRAFT_FINGERPRINT,
      '******',
    ]);
    expect(buildGenerationBackendStatusQueryKey([], '******')).toEqual(
      GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY,
    );
    expect(buildGenerationBackendStatusQueryKey(DRAFT_ITEMS, '******')).toEqual(
      buildGenerationBackendPreviewStatusQueryKey(DRAFT_FINGERPRINT, '******'),
    );
    expect(GENERATION_BACKEND_STATUS_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(GENERATION_BACKEND_STATUS_CANCEL).toEqual({ silent: true, revert: false });
    expect(GENERATION_BACKEND_STATUS_PREVIEW_DEBOUNCE_MS).toBe(500);

    const controller = new AbortController();
    await fetchGenerationBackendStatus({ items: [], maskToken: '******', signal: controller.signal });
    expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1);
    expect(getGenerationBackendStatus.mock.calls[0]).toEqual([]);
    expect(previewGenerationBackendStatus).not.toHaveBeenCalled();

    await fetchGenerationBackendStatus({
      items: DRAFT_ITEMS,
      maskToken: '******',
      signal: controller.signal,
    });
    expect(previewGenerationBackendStatus).toHaveBeenCalledTimes(1);
    expect(previewGenerationBackendStatus).toHaveBeenCalledWith({
      items: [{ key: 'GENERATION_BACKEND', value: 'opencode_cli' }],
      maskToken: '******',
    });
    expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1);
    expect(testGenerationBackend).not.toHaveBeenCalled();
  });

  it('is not barrel-exported and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useGenerationBackendStatusQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useGenerationBackendStatusQuery([], '******'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['generation-backend', 'status', 'saved']);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
      expect(scheduled.refetchInterval).toBeUndefined();
    }
    expect(
      client.getQueryCache().find({
        queryKey: GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(getGenerationBackendStatus.mock.calls[0]).toEqual([]);
    expect(result.current).not.toHaveProperty('isRefreshing');
    expect(previewGenerationBackendStatus).not.toHaveBeenCalled();
    expect(testGenerationBackend).not.toHaveBeenCalled();
  });

  it('empty items GET once and never preview; non-empty items preview POST and never GET', async () => {
    const { wrapper } = createWrapper();
    const saved = renderHook(() => useGenerationBackendStatusQuery([], '******'), { wrapper });
    await waitFor(() => expect(saved.result.current.isLoading).toBe(false));
    expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1);
    expect(previewGenerationBackendStatus).not.toHaveBeenCalled();
    expect(saved.result.current.status?.primaryBackendId).toBe('codex_cli');
    saved.unmount();

    const preview = renderHook(
      () => useGenerationBackendStatusQuery(DRAFT_ITEMS, 'secret-mask'),
      { wrapper },
    );
    await waitFor(() => expect(preview.result.current.isLoading).toBe(false));
    expect(previewGenerationBackendStatus).toHaveBeenCalledTimes(1);
    expect(previewGenerationBackendStatus).toHaveBeenCalledWith({
      items: [{ key: 'GENERATION_BACKEND', value: 'opencode_cli' }],
      maskToken: 'secret-mask',
    });
    expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1);
    expect(preview.result.current.status?.primaryBackendId).toBe('opencode_cli');
    expect(testGenerationBackend).not.toHaveBeenCalled();
  });

  it('same-key refresh cancel+remove then fetchQuery', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useGenerationBackendStatusQuery([], '******'), { wrapper });

    await waitFor(() => expect(result.current.status?.primaryBackendId).toBe('codex_cli'));
    expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1);

    const pending = createDeferred<GenerationBackendStatusResponse>();
    getGenerationBackendStatus.mockReturnValueOnce(pending.promise);
    await act(async () => {
      void result.current.load();
    });
    await waitFor(() => expect(result.current.isLoading).toBe(true));

    await act(async () => {
      pending.resolve(statusFor('codex_cli'));
      await pending.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    expect(cancelSpy).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();
    const cancelOrders = cancelSpy.mock.invocationCallOrder;
    const removeOrders = removeSpy.mock.invocationCallOrder;
    const fetchOrders = fetchSpy.mock.invocationCallOrder;
    expect(Math.min(...cancelOrders)).toBeLessThan(Math.min(...fetchOrders));
    expect(Math.min(...removeOrders)).toBeLessThan(Math.min(...fetchOrders));
    assertExactGenerationBackendOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactGenerationBackendOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('key change at load() exact-removes the previous key and does not prefix-cancel', async () => {
    const first = createDeferred<GenerationBackendStatusResponse>();
    getGenerationBackendStatus.mockReturnValueOnce(first.promise);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result, rerender } = renderHook(
      ({ items, maskToken }: StatusHookProps) => (
        useGenerationBackendStatusQuery(items, maskToken)
      ),
      { wrapper, initialProps: { items: [] as StatusHookProps['items'], maskToken: '******' } },
    );

    await waitFor(() => expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1));
    const previewKey = buildGenerationBackendPreviewStatusQueryKey(DRAFT_FINGERPRINT, '******');

    previewGenerationBackendStatus.mockResolvedValueOnce(statusFor('opencode_cli'));
    rerender({ items: DRAFT_ITEMS, maskToken: '******' });
    await act(async () => {
      await result.current.load();
    });
    await waitFor(() => expect(previewGenerationBackendStatus).toHaveBeenCalled());

    expect(cancelSpy.mock.calls.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.exact === true
      && JSON.stringify([...filters.queryKey]) === JSON.stringify([...GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY])
    ))).toBe(true);
    expect(removeSpy.mock.calls.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.exact === true
      && JSON.stringify([...filters.queryKey]) === JSON.stringify([...GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY])
    ))).toBe(true);
    expect(removeSpy.mock.calls.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.exact === true
      && JSON.stringify([...filters.queryKey]) === JSON.stringify([...previewKey])
    ))).toBe(true);

    await act(async () => {
      first.resolve(statusFor('codex_cli'));
      await first.promise.catch(() => undefined);
    });
    expect(result.current.status?.primaryBackendId).toBe('opencode_cli');
    expect(client.getQueryState(GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY)).toBeUndefined();

    const allOps = [
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>;
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey.length === 1
      && filters.queryKey[0] === 'generation-backend'
    ))).toBe(false);
    assertExactGenerationBackendOps(allOps);
  });

  it('fails closed on a 500 even when the test client default would retry', async () => {
    getGenerationBackendStatus.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useGenerationBackendStatusQuery([], '******'), { wrapper });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(result.current.status).toBeNull();
    expect(result.current.error?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
  });

  it('does not set error when transport settles as CancelledError', async () => {
    getGenerationBackendStatus.mockRejectedValue(new CancelledError(GENERATION_BACKEND_STATUS_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useGenerationBackendStatusQuery([], '******'), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.status).toBeNull();
  });

  it('lets a newer preview win over a stale saved 200', async () => {
    const first = createDeferred<GenerationBackendStatusResponse>();
    getGenerationBackendStatus.mockReturnValueOnce(first.promise);
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ items, maskToken }: StatusHookProps) => (
        useGenerationBackendStatusQuery(items, maskToken)
      ),
      { wrapper, initialProps: { items: [] as StatusHookProps['items'], maskToken: '******' } },
    );

    await waitFor(() => expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1));
    previewGenerationBackendStatus.mockResolvedValueOnce(statusFor('litellm'));
    rerender({ items: [{ key: 'GENERATION_BACKEND', value: 'litellm' }], maskToken: '******' });
    await act(async () => {
      await result.current.load();
    });
    await waitFor(() => expect(result.current.status?.primaryBackendId).toBe('litellm'));

    await act(async () => {
      first.resolve(statusFor('codex_cli'));
      await first.promise.catch(() => undefined);
    });
    expect(result.current.status?.primaryBackendId).toBe('litellm');
    expect(result.current.error).toBeNull();
  });

  it('lets a newer GET win over a stale preview', async () => {
    const first = createDeferred<GenerationBackendStatusResponse>();
    previewGenerationBackendStatus.mockReturnValueOnce(first.promise);
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ items, maskToken }: StatusHookProps) => (
        useGenerationBackendStatusQuery(items, maskToken)
      ),
      { wrapper, initialProps: { items: DRAFT_ITEMS, maskToken: '******' } },
    );

    await waitFor(() => expect(previewGenerationBackendStatus).toHaveBeenCalledTimes(1));
    getGenerationBackendStatus.mockResolvedValueOnce(statusFor('codex_cli'));
    rerender({ items: [], maskToken: '******' });
    await act(async () => {
      await result.current.load();
    });
    await waitFor(() => expect(result.current.status?.primaryBackendId).toBe('codex_cli'));

    await act(async () => {
      first.resolve(statusFor('opencode_cli'));
      await first.promise.catch(() => undefined);
    });
    expect(result.current.status?.primaryBackendId).toBe('codex_cli');
    expect(previewGenerationBackendStatus).toHaveBeenCalledTimes(1);
    expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1);
  });

  it('lets a newer 500 win over a stale 200 so rows cannot resurrect', async () => {
    const first = createDeferred<GenerationBackendStatusResponse>();
    getGenerationBackendStatus
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(serverError());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useGenerationBackendStatusQuery([], '******'), { wrapper });

    await waitFor(() => expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load();
    });
    await waitFor(() => expect(getGenerationBackendStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.error?.status).toBe(500));
    expect(result.current.status).toBeNull();

    await act(async () => {
      first.resolve(statusFor('codex_cli'));
      await first.promise.catch(() => undefined);
    });
    expect(result.current.status).toBeNull();
    expect(result.current.error?.status).toBe(500);
  });

  it('removes the exact live key on unmount and ignores a late fulfillment', async () => {
    const pending = createDeferred<GenerationBackendStatusResponse>();
    getGenerationBackendStatus.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(
      () => useGenerationBackendStatusQuery([], '******'),
      { wrapper },
    );

    await waitFor(() => expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.resolve(statusFor('codex_cli'));
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.error).toBeNull();
    expect(result.current.status).toBeNull();
    expect(client.getQueryState(GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['generation-backend'] })).toHaveLength(0);
    expect(queryFetchStatus(client, GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY)).toBeUndefined();
  });

  it('queryFn and hook source never call testGenerationBackend', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useGenerationBackendStatusQuery(DRAFT_ITEMS, '******'),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.load();
    });
    expect(testGenerationBackend).not.toHaveBeenCalled();
    expect(result.current.status?.primaryBackendId).toBe('opencode_cli');
  });

  it('loads immediately on first mount and waits 500ms for subsequent identity changes', async () => {
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ items, maskToken }: StatusHookProps) => (
        useGenerationBackendStatusQuery(items, maskToken)
      ),
      { wrapper, initialProps: { items: [] as StatusHookProps['items'], maskToken: '******' } },
    );

    await waitFor(() => expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    vi.useFakeTimers();
    rerender({ items: DRAFT_ITEMS, maskToken: '******' });
    expect(previewGenerationBackendStatus).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(GENERATION_BACKEND_STATUS_PREVIEW_DEBOUNCE_MS - 1);
    });
    expect(previewGenerationBackendStatus).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    vi.useRealTimers();
    await waitFor(() => expect(previewGenerationBackendStatus).toHaveBeenCalledTimes(1));
    expect(previewGenerationBackendStatus).toHaveBeenCalledWith({
      items: [{ key: 'GENERATION_BACKEND', value: 'opencode_cli' }],
      maskToken: '******',
    });
    expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1);
  });

  it('lets an in-flight saved completion apply during the debounce window', async () => {
    const first = createDeferred<GenerationBackendStatusResponse>();
    getGenerationBackendStatus.mockReturnValueOnce(first.promise);
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ items, maskToken }: StatusHookProps) => (
        useGenerationBackendStatusQuery(items, maskToken)
      ),
      { wrapper, initialProps: { items: [] as StatusHookProps['items'], maskToken: '******' } },
    );

    await waitFor(() => expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1));
    vi.useFakeTimers();
    rerender({ items: DRAFT_ITEMS, maskToken: '******' });
    expect(previewGenerationBackendStatus).not.toHaveBeenCalled();

    await act(async () => {
      first.resolve(statusFor('codex_cli'));
      await first.promise.catch(() => undefined);
    });
    expect(result.current.status?.primaryBackendId).toBe('codex_cli');
    expect(previewGenerationBackendStatus).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(GENERATION_BACKEND_STATUS_PREVIEW_DEBOUNCE_MS);
    });
    vi.useRealTimers();
    await waitFor(() => expect(previewGenerationBackendStatus).toHaveBeenCalledTimes(1));
  });

  it('collapses rapid identity changes to one load after 500ms', async () => {
    const { wrapper } = createWrapper();
    const { rerender } = renderHook(
      ({ items, maskToken }: StatusHookProps) => (
        useGenerationBackendStatusQuery(items, maskToken)
      ),
      { wrapper, initialProps: { items: [] as StatusHookProps['items'], maskToken: '******' } },
    );
    await waitFor(() => expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1));

    vi.useFakeTimers();
    rerender({ items: [{ key: 'GENERATION_BACKEND', value: 'a' }], maskToken: '******' });
    rerender({ items: [{ key: 'GENERATION_BACKEND', value: 'b' }], maskToken: '******' });
    expect(previewGenerationBackendStatus).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(GENERATION_BACKEND_STATUS_PREVIEW_DEBOUNCE_MS);
    });
    vi.useRealTimers();
    await waitFor(() => expect(previewGenerationBackendStatus).toHaveBeenCalledTimes(1));
    expect(previewGenerationBackendStatus).toHaveBeenCalledWith({
      items: [{ key: 'GENERATION_BACKEND', value: 'b' }],
      maskToken: '******',
    });
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useGenerationBackendStatusQuery([], '******'), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call GET again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useGenerationBackendStatusQuery([], '******'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.refetchInterval).toBeUndefined();

    vi.useFakeTimers();
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    await flushQueryMicrotasks();

    expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1);
  });

  it('issues GET while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useGenerationBackendStatusQuery([], '******'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1);
    expect(result.current.status?.primaryBackendId).toBe('codex_cli');
  });

  it('re-GETs the saved key when maskToken changes on an empty draft', async () => {
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ items, maskToken }: StatusHookProps) => (
        useGenerationBackendStatusQuery(items, maskToken)
      ),
      { wrapper, initialProps: { items: [] as StatusHookProps['items'], maskToken: '******' } },
    );
    await waitFor(() => expect(getGenerationBackendStatus).toHaveBeenCalledTimes(1));

    vi.useFakeTimers();
    rerender({ items: [], maskToken: '########' });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(GENERATION_BACKEND_STATUS_PREVIEW_DEBOUNCE_MS);
    });
    vi.useRealTimers();
    await waitFor(() => expect(getGenerationBackendStatus).toHaveBeenCalledTimes(2));
    expect(previewGenerationBackendStatus).not.toHaveBeenCalled();
    expect(result.current.status?.primaryBackendId).toBe('codex_cli');
  });
});
