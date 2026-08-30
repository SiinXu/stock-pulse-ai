// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import {
  SCREEN_TASK_POLL_QUERY_KEY_ROOT,
  useScreenTaskPollQuery,
} from '../useScreenTaskPollQuery';

const INTERVAL_MS = 2000;
const TASK_ID = 'screen-task-1';

type DeferredVoid = ReturnType<typeof createDeferred<void>>;

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return { client: queryClient, wrapper: Wrapper };
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

function createDeferredPoll() {
  const deferreds: DeferredVoid[] = [];
  let live = 0;
  let maxLive = 0;
  let label = 'v1';
  const writes: string[] = [];
  const poll = vi.fn(async (isActive: () => boolean): Promise<true> => {
    live += 1;
    maxLive = Math.max(maxLive, live);
    const deferred = createDeferred<void>();
    deferreds.push(deferred);
    try {
      await deferred.promise;
      if (isActive()) writes.push(label);
      return true;
    } finally {
      live -= 1;
    }
  });
  return {
    poll,
    deferreds,
    writes,
    get live() {
      return live;
    },
    get maxLive() {
      return maxLive;
    },
    setLabel(next: string) {
      label = next;
    },
  };
}

async function resolveDeferred(deferred: DeferredVoid) {
  await act(async () => {
    deferred.resolve();
    await deferred.promise;
  });
}

function pollQueryOptions(client: QueryClient, taskId: string, ...restartKey: unknown[]) {
  const query = client.getQueryCache().find({
    queryKey: [...SCREEN_TASK_POLL_QUERY_KEY_ROOT, taskId, ...restartKey],
  });
  return query?.options as Record<string, unknown> | undefined;
}

describe('useScreenTaskPollQuery', () => {
  beforeEach(() => {
    onlineManager.setOnline(true);
    focusManager.setFocused(true);
  });

  afterEach(() => {
    vi.useRealTimers();
    onlineManager.setOnline(true);
    focusManager.setFocused(true);
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
  });

  it('fires the first poll immediately and the next poll 2000ms after settlement', async () => {
    vi.useFakeTimers();
    const { poll, deferreds } = createDeferredPoll();
    const { wrapper } = createWrapper();

    renderHook(
      () => useScreenTaskPollQuery({
        taskId: TASK_ID,
        restartKey: ['en'],
        poll,
        intervalMs: INTERVAL_MS,
      }),
      { wrapper },
    );

    await flushQueryMicrotasks();
    expect(poll).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(poll).toHaveBeenCalledTimes(1);
    await resolveDeferred(deferreds[0]!);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1999);
    });
    await flushQueryMicrotasks();
    expect(poll).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    await flushQueryMicrotasks();
    expect(poll).toHaveBeenCalledTimes(2);
  });

  it('does not overlap or cancel when a poll lasts longer than 2000ms', async () => {
    vi.useFakeTimers();
    const session = createDeferredPoll();
    const { wrapper } = createWrapper();

    renderHook(
      () => useScreenTaskPollQuery({
        taskId: TASK_ID,
        restartKey: ['en'],
        poll: session.poll,
        intervalMs: INTERVAL_MS,
      }),
      { wrapper },
    );

    await flushQueryMicrotasks();
    expect(session.poll).toHaveBeenCalledTimes(1);
    expect(session.live).toBe(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await flushQueryMicrotasks();
    expect(session.poll).toHaveBeenCalledTimes(1);
    expect(session.live).toBe(1);
    expect(session.maxLive).toBe(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    await resolveDeferred(session.deferreds[0]!);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await flushQueryMicrotasks();
    expect(session.poll).toHaveBeenCalledTimes(2);
    expect(session.maxLive).toBe(1);
  });

  it('aborts the old language generation and does not write after unmount', async () => {
    vi.useFakeTimers();
    const session = createDeferredPoll();
    const { wrapper } = createWrapper();

    const { rerender, unmount } = renderHook(
      ({ language }: { language: string }) => useScreenTaskPollQuery({
        taskId: TASK_ID,
        restartKey: [language],
        poll: session.poll,
        intervalMs: INTERVAL_MS,
      }),
      { wrapper, initialProps: { language: 'en' } },
    );

    await flushQueryMicrotasks();
    expect(session.poll).toHaveBeenCalledTimes(1);

    session.setLabel('zh');
    rerender({ language: 'zh' });
    await flushQueryMicrotasks();
    expect(session.poll).toHaveBeenCalledTimes(2);

    await resolveDeferred(session.deferreds[0]!);
    expect(session.writes).toEqual([]);

    await resolveDeferred(session.deferreds[1]!);
    expect(session.writes).toEqual(['zh']);

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    await flushQueryMicrotasks();
    expect(session.poll).toHaveBeenCalledTimes(2);
    expect(session.writes).toEqual(['zh']);
  });

  it('stops further polls when the task id is cleared', async () => {
    vi.useFakeTimers();
    const session = createDeferredPoll();
    const { wrapper } = createWrapper();

    const { rerender } = renderHook(
      ({ taskId }: { taskId: string | null }) => useScreenTaskPollQuery({
        taskId,
        restartKey: ['en'],
        poll: session.poll,
        intervalMs: INTERVAL_MS,
      }),
      { wrapper, initialProps: { taskId: TASK_ID as string | null } },
    );

    await flushQueryMicrotasks();
    expect(session.poll).toHaveBeenCalledTimes(1);
    await resolveDeferred(session.deferreds[0]!);

    rerender({ taskId: null });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    await flushQueryMicrotasks();
    expect(session.poll).toHaveBeenCalledTimes(1);
  });

  it('keeps the 2000ms cadence without focus refetch, retry, or reconnect extras', async () => {
    vi.useFakeTimers();
    const session = createDeferredPoll();
    const client = createAppQueryClient();
    const { wrapper } = createWrapper(client);

    renderHook(
      () => useScreenTaskPollQuery({
        taskId: TASK_ID,
        restartKey: ['en'],
        poll: session.poll,
        intervalMs: INTERVAL_MS,
      }),
      { wrapper },
    );

    await flushQueryMicrotasks();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const options = pollQueryOptions(client, TASK_ID, 'en');
    expect(options?.retry).toBe(false);
    expect(options?.refetchOnWindowFocus).toBe(false);
    expect(options?.refetchInterval).toBe(INTERVAL_MS);
    expect(options?.refetchIntervalInBackground).toBe(true);
    expect(options?.networkMode).toBe('always');
    expect(options?.staleTime ?? 0).toBe(0);
    expect(options?.queryKey).toEqual([...SCREEN_TASK_POLL_QUERY_KEY_ROOT, TASK_ID, 'en']);

    await resolveDeferred(session.deferreds[0]!);
    expect(session.poll).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
    });
    await flushQueryMicrotasks();
    expect(session.poll).toHaveBeenCalledTimes(1);

    await act(async () => {
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });
    await flushQueryMicrotasks();
    expect(session.poll).toHaveBeenCalledTimes(1);
  });

  it('continues polling while hidden and while Query reports the browser offline', async () => {
    vi.useFakeTimers();
    const session = createDeferredPoll();
    const { wrapper } = createWrapper();

    onlineManager.setOnline(false);
    focusManager.setFocused(false);
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });

    renderHook(
      () => useScreenTaskPollQuery({
        taskId: TASK_ID,
        restartKey: ['en'],
        poll: session.poll,
        intervalMs: INTERVAL_MS,
      }),
      { wrapper },
    );

    await flushQueryMicrotasks();
    expect(session.poll).toHaveBeenCalledTimes(1);
    await resolveDeferred(session.deferreds[0]!);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(INTERVAL_MS);
    });
    await flushQueryMicrotasks();
    expect(session.poll).toHaveBeenCalledTimes(2);
  });

  it('does not immediately retry a thrown poll and continues after settlement', async () => {
    vi.useFakeTimers();
    const deferreds: DeferredVoid[] = [];
    const poll = vi.fn(async () => {
      const deferred = createDeferred<void>();
      deferreds.push(deferred);
      await deferred.promise;
      throw new Error('poll failed');
    });
    const { wrapper } = createWrapper();

    renderHook(
      () => useScreenTaskPollQuery({
        taskId: TASK_ID,
        restartKey: ['en'],
        poll,
        intervalMs: INTERVAL_MS,
      }),
      { wrapper },
    );

    await flushQueryMicrotasks();
    expect(poll).toHaveBeenCalledTimes(1);
    await act(async () => {
      deferreds[0]!.reject(new Error('poll failed'));
      await deferreds[0]!.promise.catch(() => undefined);
    });
    await flushQueryMicrotasks();
    expect(poll).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(INTERVAL_MS);
    });
    await flushQueryMicrotasks();
    expect(poll).toHaveBeenCalledTimes(2);
  });
});
