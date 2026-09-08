// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createParsedApiError } from '../../api/error';
import { securityAuditApi } from '../../api/securityAudit';
import type { UiLanguage } from '../../i18n/uiText';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { SecurityAuditEvent, SecurityAuditEventPage } from '../../types/securityAudit';
import {
  SECURITY_AUDIT_CANCEL,
  SECURITY_AUDIT_DEFAULT_PAGE_SIZE,
  SECURITY_AUDIT_QUERY_KEY_ROOT,
  SECURITY_AUDIT_QUERY_SCHEDULE,
  buildSecurityAuditListQuery,
  buildSecurityAuditQueryKey,
  fetchSecurityAuditEvents,
  useSecurityAuditQuery,
} from '../useSecurityAuditQuery';

vi.mock('../../api/securityAudit', () => ({
  securityAuditApi: {
    list: vi.fn(),
  },
}));

const listMock = vi.mocked(securityAuditApi.list);

function auditEvent(overrides: Partial<SecurityAuditEvent> = {}): SecurityAuditEvent {
  return {
    id: 12,
    schemaVersion: 'security-audit-v1',
    occurredAt: '2026-07-24T12:00:00Z',
    eventType: 'auth.login',
    phase: 'completion',
    actor: { type: 'admin', id: 'local_admin' },
    executionId: 'exec-1',
    action: 'login',
    target: { type: 'session', id: 'web' },
    outcome: 'success',
    reasonCode: 'authenticated',
    correlationId: '0123456789abcdef0123456789abcdef',
    metadata: { keySample: ['AUTH_ENABLED'] },
    ...overrides,
  };
}

function eventPage(overrides: Partial<SecurityAuditEventPage> = {}): SecurityAuditEventPage {
  const items = overrides.items ?? [auditEvent()];
  return {
    page: 1,
    pageSize: 50,
    total: items.length,
    items,
    ...overrides,
  };
}

function serverError(): Error {
  return Object.assign(new Error('server'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'security audit unavailable' },
    },
  });
}

function authRequiredError() {
  return createParsedApiError({
    title: 'Security audit requires administrator authentication',
    message: 'Auth required',
    status: 403,
    code: 'security_audit_auth_required',
    category: 'http_error',
  });
}

function genericForbiddenError(): Error {
  return Object.assign(new Error('forbidden'), {
    response: {
      status: 403,
      data: { error: 'forbidden', message: 'not allowed', code: 'forbidden' },
    },
  });
}

const DEFAULT_KEY = buildSecurityAuditQueryKey(1, 50, '', '', '');

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? createAppQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return { client: queryClient, wrapper: Wrapper };
}

function queryOptions(
  client: QueryClient,
  queryKey: readonly unknown[] = DEFAULT_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactSecurityAuditOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'security-audit' && key.length === 1).toBe(false);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'outbound-activity').toBe(false);
    expect(key[0] === 'kronos').toBe(false);
    expect(key[0] === 'data-providers').toBe(false);
    expect(key[0] === 'scorecard').toBe(false);
    expect(key[0] === 'notifications').toBe(false);
    if (key[0] === 'security-audit') {
      expect(filters?.exact).toBe(true);
      expect(key[0]).toBe('security-audit');
      expect(key[1]).toBe('events');
      expect(key).toHaveLength(7);
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

describe('useSecurityAuditQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    listMock.mockResolvedValue(eventPage());
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

  it('pins the exact paginated key, schedule, and cancel flags', async () => {
    expect([...SECURITY_AUDIT_QUERY_KEY_ROOT]).toEqual(['security-audit', 'events']);
    expect(SECURITY_AUDIT_QUERY_KEY_ROOT).toHaveLength(2);
    expect(SECURITY_AUDIT_DEFAULT_PAGE_SIZE).toBe(50);
    expect([...buildSecurityAuditQueryKey(1, 50, '', '', '')]).toEqual([
      'security-audit', 'events', 1, 50, 'all', 'all', 'none',
    ]);
    expect([...buildSecurityAuditQueryKey(2, 25, '  auth.login  ', 'denied', '  corr-1  ')]).toEqual([
      'security-audit', 'events', 2, 25, 'auth.login', 'denied', 'corr-1',
    ]);
    expect(SECURITY_AUDIT_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(SECURITY_AUDIT_CANCEL).toEqual({ silent: true, revert: false });
    expect(buildSecurityAuditListQuery(1, 50, '', '', '')).toEqual({
      page: 1,
      pageSize: 50,
    });
  });

  it('calls securityAuditApi.list with the applied query object and no AbortSignal', async () => {
    const controller = new AbortController();
    await fetchSecurityAuditEvents({
      page: 1,
      pageSize: 50,
      eventType: '',
      outcome: '',
      correlationId: '',
      signal: controller.signal,
    });
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(listMock.mock.calls[0]).toEqual([{ page: 1, pageSize: 50 }]);
    expect(listMock.mock.calls[0]).toHaveLength(1);

    listMock.mockClear();
    await fetchSecurityAuditEvents({
      page: 2,
      pageSize: 25,
      eventType: 'system_config.write',
      outcome: 'denied',
      correlationId: 'corr-1',
      signal: controller.signal,
    });
    expect(listMock.mock.calls[0]).toEqual([{
      page: 2,
      pageSize: 25,
      eventType: 'system_config.write',
      outcome: 'denied',
      correlationId: 'corr-1',
    }]);
    expect(listMock.mock.calls[0]).toHaveLength(1);
  });

  it('is not barrel-exported, uses fetchQuery, and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useSecurityAuditQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['security-audit', 'events', 1, 50, 'all', 'all', 'none']);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
    }
    expect(
      client.getQueryCache().find({
        queryKey: DEFAULT_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(listMock.mock.calls[0]).toEqual([{ page: 1, pageSize: 50 }]);
  });

  it('mounts once at page 1 / pageSize 50 with no optional filters', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(listMock.mock.calls[0]).toEqual([{ page: 1, pageSize: 50 }]);
    expect(result.current.page).toBe(1);
    expect(result.current.pageSize).toBe(50);
    expect(result.current.isRefreshing).toBe(false);
  });

  it('treats a 200 with rows as success', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0]?.id).toBe(12);
    expect(result.current.total).toBe(1);
    expect(result.current.loadError).toBeNull();
  });

  it('treats empty 200 items/total as success and does not set loadError', async () => {
    listMock.mockResolvedValue(eventPage({ items: [], total: 0 }));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.loadError).toBeNull();
    expect(result.current.loadError?.code).not.toBe('security_audit_auth_required');
    expect(result.current.isRefreshing).toBe(false);
  });

  it('removes the exact live key on unmount and ignores a late 200', async () => {
    const pending = createDeferred<SecurityAuditEventPage>();
    listMock.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });

    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.resolve(eventPage({ items: [auditEvent({ id: 99 })] }));
      await pending.promise;
      await Promise.resolve();
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.loadError).toBeNull();
    expect(client.getQueryState(DEFAULT_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['security-audit'] })).toHaveLength(0);
    expect(queryFetchStatus(client, DEFAULT_KEY)).toBeUndefined();
  });

  it('removes the exact live key on unmount and ignores a late 500', async () => {
    const pending = createDeferred<SecurityAuditEventPage>();
    listMock.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });

    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.loadError).toBeNull();
    expect(result.current.items).toEqual([]);
    expect(client.getQueryState(DEFAULT_KEY)).toBeUndefined();
    expect(queryFetchStatus(client, DEFAULT_KEY)).toBeUndefined();
  });

  it('lets a newer 500 win over a stale 200 so prior rows cannot resurrect', async () => {
    const first = createDeferred<SecurityAuditEventPage>();
    listMock
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(serverError());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });

    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.loadError?.status).toBe(500));

    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);

    await act(async () => {
      first.resolve(eventPage({ items: [auditEvent({ id: 77 })] }));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.loadError?.status).toBe(500);
  });

  it('lets a newer empty 200 win over a stale 500 so ApiErrorAlert cannot replace it', async () => {
    const first = createDeferred<SecurityAuditEventPage>();
    listMock
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(eventPage({ items: [], total: 0 }));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });

    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.loadError).toBeNull();
    expect(result.current.isRefreshing).toBe(false);

    await act(async () => {
      first.reject(serverError());
      await first.promise.catch(() => undefined);
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.loadError).toBeNull();
  });

  it('parses security_audit_auth_required onto loadError and keeps generic 403 distinct', async () => {
    listMock.mockRejectedValueOnce(authRequiredError());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });

    await waitFor(() => expect(result.current.loadError).not.toBeNull());
    expect(result.current.loadError?.code).toBe('security_audit_auth_required');
    expect(result.current.loadError?.status).toBe(403);
    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);

    listMock.mockRejectedValueOnce(genericForbiddenError());
    await act(async () => {
      await result.current.load('refresh');
    });
    await waitFor(() => expect(result.current.loadError?.code).not.toBe('security_audit_auth_required'));
    expect(result.current.loadError?.status).toBe(403);
    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
  });

  it('same-key refresh cancel+remove then fetchQuery and keeps rows until the live generation', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });

    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);

    const pending = createDeferred<SecurityAuditEventPage>();
    listMock.mockReturnValueOnce(pending.promise);
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.isLoading).toBe(false);
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0]?.id).toBe(12);

    await act(async () => {
      pending.resolve(eventPage({ items: [auditEvent({ id: 44 })] }));
      await pending.promise;
    });
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
    expect(result.current.items[0]?.id).toBe(44);
    expect(result.current.loadError).toBeNull();
    expect(fetchSpy).toHaveBeenCalled();
    expect(cancelSpy).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();

    const cancelOrders = cancelSpy.mock.invocationCallOrder;
    const removeOrders = removeSpy.mock.invocationCallOrder;
    const fetchOrders = fetchSpy.mock.invocationCallOrder;
    expect(Math.min(...cancelOrders)).toBeLessThan(Math.min(...fetchOrders));
    expect(Math.min(...removeOrders)).toBeLessThan(Math.min(...fetchOrders));
    assertExactSecurityAuditOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactSecurityAuditOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('page and filter changes cancel+remove the previous exact key; stale page-1 cannot overwrite page-2', async () => {
    const first = createDeferred<SecurityAuditEventPage>();
    listMock.mockReturnValueOnce(first.promise);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });

    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));
    const page1Key = buildSecurityAuditQueryKey(1, 50, '', '', '');
    const page2Key = buildSecurityAuditQueryKey(2, 50, '', '', '');
    const filterKey = buildSecurityAuditQueryKey(1, 50, 'system_config.write', '', '');

    listMock.mockResolvedValueOnce(eventPage({
      page: 2,
      total: 2,
      items: [auditEvent({ id: 2 })],
    }));
    await act(async () => {
      void result.current.load('refresh', { page: 2 });
    });
    await waitFor(() => expect(result.current.page).toBe(2));
    expect(result.current.items[0]?.id).toBe(2);
    expect(listMock.mock.calls[1]).toEqual([{ page: 2, pageSize: 50 }]);

    expect(cancelSpy.mock.calls.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.exact === true
      && JSON.stringify([...filters.queryKey]) === JSON.stringify([...page1Key])
    ))).toBe(true);
    expect(removeSpy.mock.calls.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.exact === true
      && JSON.stringify([...filters.queryKey]) === JSON.stringify([...page1Key])
    ))).toBe(true);

    await act(async () => {
      first.resolve(eventPage({ page: 1, total: 99, items: [auditEvent({ id: 1 })] }));
      await first.promise.catch(() => undefined);
    });
    expect(result.current.page).toBe(2);
    expect(result.current.items[0]?.id).toBe(2);
    expect(result.current.total).toBe(2);

    listMock.mockResolvedValueOnce(eventPage({ items: [], total: 0 }));
    await act(async () => {
      await result.current.load('refresh', {
        page: 1,
        eventType: 'system_config.write',
      });
    });
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(3));
    expect(listMock.mock.calls[2]).toEqual([{
      page: 1,
      pageSize: 50,
      eventType: 'system_config.write',
    }]);
    expect(cancelSpy.mock.calls.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.exact === true
      && JSON.stringify([...filters.queryKey]) === JSON.stringify([...page2Key])
    ))).toBe(true);
    expect(client.getQueryState(filterKey)?.data).toEqual(eventPage({ items: [], total: 0 }));
    assertExactSecurityAuditOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('fails closed on a 500 even when the test client default would retry', async () => {
    listMock.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });

    await waitFor(() => expect(result.current.loadError).not.toBeNull());
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);
  });

  it('does not set loadError when the list settles as CancelledError', async () => {
    listMock.mockRejectedValue(new CancelledError(SECURITY_AUDIT_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.loadError).toBeNull();
    expect(result.current.loadError?.code).not.toBe('security_audit_auth_required');
    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
  });

  it('never prefix-cancels or prefix-removes sibling Query roots', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.load('refresh');
    });
    await act(async () => {
      await result.current.load('refresh', { page: 2 });
    });

    const allOps = [
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>;
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey.length === 1
      && filters.queryKey[0] === 'security-audit'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'settings'
    ))).toBe(false);
    assertExactSecurityAuditOps(allOps);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(listMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(listMock).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call list again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listMock).toHaveBeenCalledTimes(1);
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

    expect(listMock).toHaveBeenCalledTimes(1);
  });

  it('issues the list while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useSecurityAuditQuery('en'), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
    expect(result.current.items).toHaveLength(1);
  });

  it('uses language only to parse the live generation and does not refetch on language change', async () => {
    const errorModule = await import('../../api/error');
    const liveParseSpy = vi.spyOn(errorModule, 'getParsedApiError');
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ language }: { language: UiLanguage }) => useSecurityAuditQuery(language),
      { wrapper, initialProps: { language: 'zh' as UiLanguage } },
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listMock).toHaveBeenCalledTimes(1);

    rerender({ language: 'en' });
    await flushQueryMicrotasks();
    expect(listMock).toHaveBeenCalledTimes(1);

    listMock.mockRejectedValueOnce(serverError());
    await act(async () => {
      await result.current.load('refresh');
    });
    await waitFor(() => expect(result.current.loadError).not.toBeNull());
    expect(result.current.loadError?.status).toBe(500);
    expect(liveParseSpy).toHaveBeenCalled();
    expect(liveParseSpy.mock.calls.some(([, language]) => language === 'en')).toBe(true);
    expect(listMock).toHaveBeenCalledTimes(2);
    liveParseSpy.mockRestore();
  });
});
