// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { agentApi, type AgentModelsResponse } from '../../api/agent';
import { capabilitiesApi, type CapabilityListResponse } from '../../api/capabilities';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import {
  AGENT_MODELS_QUERY_KEY,
  CAPABILITIES_RUNTIME_QUERY_KEY,
  RUNTIME_CAPABILITIES_CANCEL,
  RUNTIME_CAPABILITIES_QUERY_SCHEDULE,
  fetchAgentModels,
  fetchCapabilitiesRuntime,
  useRuntimeCapabilitiesQuery,
} from '../useRuntimeCapabilitiesQuery';

vi.mock('../../api/capabilities', () => ({
  capabilitiesApi: {
    list: vi.fn(),
  },
}));

vi.mock('../../api/agent', () => ({
  agentApi: {
    getModels: vi.fn(),
  },
}));

const listMock = vi.mocked(capabilitiesApi.list);
const getModelsMock = vi.mocked(agentApi.getModels);

function capabilityResponse(overrides: Partial<CapabilityListResponse> = {}): CapabilityListResponse {
  return {
    schema_version: 'capability-inventory/v1',
    partial: false,
    sources: [{ source: 'tool', state: 'ok', generation: '1', as_of: '2026-08-13' }],
    items: [{
      id: 'tool:market.quote',
      domain: 'tool',
      type: 'agent_tool',
      owner: 'agent-tools',
      provider: 'core',
      version: '1',
      source_generation: '1',
      as_of: '2026-08-13',
      registered: true,
      executable: true,
      display_name: 'Market quote',
    }],
    total: 1,
    executable_count: 1,
    non_executable_count: 0,
    unknown_executable_count: 0,
    ...overrides,
  } as CapabilityListResponse;
}

function modelResponse(overrides: Partial<AgentModelsResponse> = {}): AgentModelsResponse {
  return {
    models: [{
      deployment_id: 'primary-agent',
      deployment_name: 'Primary Agent',
      model: 'provider/model',
      provider: 'provider',
      source: 'AGENT_LITELLM_MODEL',
      api_base: null,
      is_primary: true,
      is_fallback: false,
    }],
    ...overrides,
  } as AgentModelsResponse;
}

function serverError(message = 'runtime capabilities unavailable'): Error {
  return Object.assign(new Error('server'), {
    response: {
      status: 500,
      data: { error: 'internal', message },
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
  queryKey: readonly unknown[],
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function assertExactRuntimeOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'capabilities' && key.length === 1).toBe(false);
    expect(key[0] === 'agent-models' && key.length === 1).toBe(false);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'security-audit').toBe(false);
    expect(key[0] === 'outbound-activity').toBe(false);
    expect(key[0] === 'kronos').toBe(false);
    expect(key[0] === 'data-providers').toBe(false);
    expect(key[0] === 'scorecard').toBe(false);
    expect(key[0] === 'notifications').toBe(false);
    expect(key[0] === 'agent-run-feedback').toBe(false);
    if (key[0] === 'capabilities') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['capabilities', 'runtime']);
      expect(key).toHaveLength(2);
    }
    if (key[0] === 'agent-models') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['agent-models', 'deployments']);
      expect(key).toHaveLength(2);
    }
  }
}

function isExactKey(
  filters: { queryKey?: readonly unknown[]; exact?: boolean } | undefined,
  expected: readonly unknown[],
): boolean {
  const key = filters?.queryKey ?? [];
  return filters?.exact === true
    && key.length === expected.length
    && expected.every((item, index) => key[index] === item);
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

describe('useRuntimeCapabilitiesQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    listMock.mockResolvedValue(capabilityResponse());
    getModelsMock.mockResolvedValue(modelResponse());
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

  it('pins the exact keys, schedule, cancel flags, and transport with no extra args', async () => {
    expect([...CAPABILITIES_RUNTIME_QUERY_KEY]).toEqual(['capabilities', 'runtime']);
    expect(CAPABILITIES_RUNTIME_QUERY_KEY).toHaveLength(2);
    expect([...AGENT_MODELS_QUERY_KEY]).toEqual(['agent-models', 'deployments']);
    expect(AGENT_MODELS_QUERY_KEY).toHaveLength(2);
    expect(RUNTIME_CAPABILITIES_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(RUNTIME_CAPABILITIES_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchCapabilitiesRuntime({ signal: controller.signal });
    await fetchAgentModels({ signal: controller.signal });
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(getModelsMock).toHaveBeenCalledTimes(1);
    expect(listMock.mock.calls[0]).toEqual([]);
    expect(getModelsMock.mock.calls[0]).toEqual([]);
  });

  it('mounts both GETs once, writes snapshots, and does not mount live observers', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useRuntimeCapabilitiesQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });
    await waitFor(() => expect(result.current.capabilitiesLoading).toBe(false));
    await waitFor(() => expect(result.current.modelsLoading).toBe(false));

    expect(listMock).toHaveBeenCalledTimes(1);
    expect(getModelsMock).toHaveBeenCalledTimes(1);
    expect(listMock.mock.calls[0]).toEqual([]);
    expect(getModelsMock.mock.calls[0]).toEqual([]);
    expect(result.current.capabilities?.items?.[0]?.display_name).toBe('Market quote');
    expect(result.current.models?.[0]?.deployment_name).toBe('Primary Agent');
    expect(result.current.capabilitiesError).toBeNull();
    expect(result.current.modelsError).toBeNull();

    const fetchKeys = fetchSpy.mock.calls.map(([options]) => [...(options.queryKey as readonly unknown[])]);
    expect(fetchKeys).toEqual(expect.arrayContaining([
      ['capabilities', 'runtime'],
      ['agent-models', 'deployments'],
    ]));
    expect(fetchKeys.every((key) => !key.includes('en') && !key.includes('zh'))).toBe(true);
    for (const [options] of fetchSpy.mock.calls) {
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
    }
    expect(
      client.getQueryCache().find({
        queryKey: CAPABILITIES_RUNTIME_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(
      client.getQueryCache().find({
        queryKey: AGENT_MODELS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('removes both exact keys on unmount and ignores a late 500', async () => {
    const pendingCapabilities = createDeferred<CapabilityListResponse>();
    const pendingModels = createDeferred<AgentModelsResponse>();
    listMock.mockReturnValueOnce(pendingCapabilities.promise);
    getModelsMock.mockReturnValueOnce(pendingModels.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });

    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));
    expect(getModelsMock).toHaveBeenCalledTimes(1);
    unmount();

    await act(async () => {
      pendingCapabilities.reject(serverError('late capabilities'));
      pendingModels.reject(serverError('late models'));
      await pendingCapabilities.promise.catch(() => undefined);
      await pendingModels.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.capabilitiesError).toBeNull();
    expect(result.current.modelsError).toBeNull();
    expect(result.current.capabilities).toBeNull();
    expect(result.current.models).toBeNull();
    expect(client.getQueryState(CAPABILITIES_RUNTIME_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryState(AGENT_MODELS_QUERY_KEY)).toBeUndefined();
  });

  it('retries failed models independently from capabilities', async () => {
    getModelsMock
      .mockRejectedValueOnce(serverError('models unavailable'))
      .mockResolvedValueOnce(modelResponse());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });

    await waitFor(() => expect(result.current.modelsError).not.toBeNull());
    expect(result.current.capabilities?.items?.[0]?.display_name).toBe('Market quote');
    expect(result.current.models).toBeNull();
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(getModelsMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.reloadModels();
    });

    expect(result.current.models?.[0]?.deployment_name).toBe('Primary Agent');
    expect(result.current.modelsError).toBeNull();
    expect(result.current.capabilities?.items?.[0]?.display_name).toBe('Market quote');
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(getModelsMock).toHaveBeenCalledTimes(2);
  });

  it('treats partial capability 200 as success when models fail', async () => {
    listMock.mockResolvedValueOnce(capabilityResponse({
      partial: true,
      sources: [{
        source: 'data',
        state: 'error',
        generation: '1',
        as_of: '2026-08-13',
        error_code: 'probe_failed',
      }],
    }));
    getModelsMock.mockRejectedValueOnce(serverError('models unavailable'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });

    await waitFor(() => expect(result.current.capabilitiesLoading).toBe(false));
    await waitFor(() => expect(result.current.modelsError).not.toBeNull());
    expect(result.current.capabilities?.partial).toBe(true);
    expect(result.current.capabilities?.items?.[0]?.display_name).toBe('Market quote');
    expect(result.current.capabilitiesError).toBeNull();
    expect(result.current.models).toBeNull();
  });

  it('preserves the last capabilities snapshot when a refresh fails', async () => {
    listMock
      .mockResolvedValueOnce(capabilityResponse())
      .mockRejectedValueOnce(serverError('capabilities unavailable'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });
    await waitFor(() => expect(result.current.capabilities?.items?.[0]?.display_name).toBe('Market quote'));

    await act(async () => {
      await result.current.reloadCapabilities();
    });

    expect(result.current.capabilities?.items?.[0]?.display_name).toBe('Market quote');
    expect(result.current.capabilitiesError?.status).toBe(500);
    expect(result.current.capabilitiesLoading).toBe(false);
    expect(result.current.models?.[0]?.deployment_name).toBe('Primary Agent');
  });

  it('preserves the last models snapshot when a refresh fails', async () => {
    getModelsMock
      .mockResolvedValueOnce(modelResponse())
      .mockRejectedValueOnce(serverError('models unavailable'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });
    await waitFor(() => expect(result.current.models?.[0]?.deployment_name).toBe('Primary Agent'));

    await act(async () => {
      await result.current.reloadModels();
    });

    expect(result.current.models?.[0]?.deployment_name).toBe('Primary Agent');
    expect(result.current.modelsError?.status).toBe(500);
    expect(result.current.modelsLoading).toBe(false);
    expect(result.current.capabilities?.items?.[0]?.display_name).toBe('Market quote');
  });

  it('fails closed on the first capabilities or models 500 with no snapshot', async () => {
    listMock.mockRejectedValueOnce(serverError('capabilities unavailable'));
    getModelsMock.mockRejectedValueOnce(serverError('models unavailable'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });

    await waitFor(() => expect(result.current.capabilitiesError).not.toBeNull());
    await waitFor(() => expect(result.current.modelsError).not.toBeNull());
    expect(result.current.capabilities).toBeNull();
    expect(result.current.models).toBeNull();
    expect(result.current.capabilitiesError?.status).toBe(500);
    expect(result.current.modelsError?.status).toBe(500);
    expect(result.current.capabilitiesLoading).toBe(false);
    expect(result.current.modelsLoading).toBe(false);
  });

  it('lets a newer capabilities 500 win over a stale 200 with no prior snapshot', async () => {
    const first = createDeferred<CapabilityListResponse>();
    listMock
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(serverError('newer capabilities'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });

    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.reloadCapabilities();
    });
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.capabilitiesError?.status).toBe(500));

    expect(result.current.capabilities).toBeNull();
    expect(result.current.capabilitiesLoading).toBe(false);

    await act(async () => {
      first.resolve(capabilityResponse({
        items: [{
          id: 'tool:stale',
          domain: 'tool',
          type: 'agent_tool',
          owner: 'agent-tools',
          provider: 'core',
          version: '1',
          source_generation: '1',
          as_of: '2026-08-13',
          registered: true,
          executable: true,
          display_name: 'Stale quote',
        }],
      } as Partial<CapabilityListResponse>));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.capabilities).toBeNull();
    expect(result.current.capabilitiesError?.status).toBe(500);
  });

  it('lets a newer capabilities 500 win over a stale refresh 200 while keeping last-good', async () => {
    const refresh = createDeferred<CapabilityListResponse>();
    listMock
      .mockResolvedValueOnce(capabilityResponse())
      .mockReturnValueOnce(refresh.promise)
      .mockRejectedValueOnce(serverError('newer capabilities'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });
    await waitFor(() => expect(result.current.capabilities?.items?.[0]?.display_name).toBe('Market quote'));

    await act(async () => {
      void result.current.reloadCapabilities();
    });
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2));
    await act(async () => {
      void result.current.reloadCapabilities();
    });
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(result.current.capabilitiesError?.status).toBe(500));

    expect(result.current.capabilities?.items?.[0]?.display_name).toBe('Market quote');

    await act(async () => {
      refresh.resolve(capabilityResponse({
        items: [{
          id: 'tool:stale-refresh',
          domain: 'tool',
          type: 'agent_tool',
          owner: 'agent-tools',
          provider: 'core',
          version: '1',
          source_generation: '1',
          as_of: '2026-08-13',
          registered: true,
          executable: true,
          display_name: 'Stale refresh',
        }],
      } as Partial<CapabilityListResponse>));
      await refresh.promise.catch(() => undefined);
    });

    expect(result.current.capabilities?.items?.[0]?.display_name).toBe('Market quote');
    expect(result.current.capabilitiesError?.status).toBe(500);
  });

  it('does not set either error or clear last-good on silent CancelledError', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });
    await waitFor(() => expect(result.current.capabilities?.items?.[0]?.display_name).toBe('Market quote'));
    await waitFor(() => expect(result.current.models?.[0]?.deployment_name).toBe('Primary Agent'));

    listMock.mockRejectedValueOnce(new CancelledError(RUNTIME_CAPABILITIES_CANCEL));
    getModelsMock.mockRejectedValueOnce(new CancelledError(RUNTIME_CAPABILITIES_CANCEL));

    await act(async () => {
      await result.current.reloadCapabilities();
      await result.current.reloadModels();
    });

    expect(result.current.capabilitiesError).toBeNull();
    expect(result.current.modelsError).toBeNull();
    expect(result.current.capabilities?.items?.[0]?.display_name).toBe('Market quote');
    expect(result.current.models?.[0]?.deployment_name).toBe('Primary Agent');
    expect(result.current.capabilitiesLoading).toBe(false);
    expect(result.current.modelsLoading).toBe(false);
  });

  it('same-key capabilities refresh cancel+remove then fetchQuery without touching models', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });
    await waitFor(() => expect(result.current.capabilitiesLoading).toBe(false));
    await waitFor(() => expect(result.current.modelsLoading).toBe(false));

    cancelSpy.mockClear();
    removeSpy.mockClear();
    fetchSpy.mockClear();

    await act(async () => {
      await result.current.reloadCapabilities();
    });

    expect(fetchSpy).toHaveBeenCalled();
    expect(cancelSpy).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();
    expect(Math.min(...cancelSpy.mock.invocationCallOrder))
      .toBeLessThan(Math.min(...fetchSpy.mock.invocationCallOrder));
    expect(Math.min(...removeSpy.mock.invocationCallOrder))
      .toBeLessThan(Math.min(...fetchSpy.mock.invocationCallOrder));

    expect(cancelSpy.mock.calls.every(([filters]) => (
      isExactKey(filters, CAPABILITIES_RUNTIME_QUERY_KEY)
    ))).toBe(true);
    expect(removeSpy.mock.calls.every(([filters]) => (
      isExactKey(filters, CAPABILITIES_RUNTIME_QUERY_KEY)
    ))).toBe(true);
    expect(fetchSpy.mock.calls.every(([options]) => (
      Array.isArray(options.queryKey)
      && options.queryKey[0] === 'capabilities'
      && options.queryKey[1] === 'runtime'
    ))).toBe(true);
    expect(cancelSpy.mock.calls.some(([filters]) => (
      isExactKey(filters, AGENT_MODELS_QUERY_KEY)
    ))).toBe(false);
    expect(removeSpy.mock.calls.some(([filters]) => (
      isExactKey(filters, AGENT_MODELS_QUERY_KEY)
    ))).toBe(false);
    expect(listMock).toHaveBeenCalledTimes(2);
    expect(getModelsMock).toHaveBeenCalledTimes(1);
    assertExactRuntimeOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactRuntimeOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('same-key models refresh cancel+remove then fetchQuery without touching capabilities', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });
    await waitFor(() => expect(result.current.capabilitiesLoading).toBe(false));
    await waitFor(() => expect(result.current.modelsLoading).toBe(false));

    cancelSpy.mockClear();
    removeSpy.mockClear();
    fetchSpy.mockClear();

    await act(async () => {
      await result.current.reloadModels();
    });

    expect(Math.min(...cancelSpy.mock.invocationCallOrder))
      .toBeLessThan(Math.min(...fetchSpy.mock.invocationCallOrder));
    expect(Math.min(...removeSpy.mock.invocationCallOrder))
      .toBeLessThan(Math.min(...fetchSpy.mock.invocationCallOrder));
    expect(cancelSpy.mock.calls.every(([filters]) => (
      isExactKey(filters, AGENT_MODELS_QUERY_KEY)
    ))).toBe(true);
    expect(removeSpy.mock.calls.every(([filters]) => (
      isExactKey(filters, AGENT_MODELS_QUERY_KEY)
    ))).toBe(true);
    expect(cancelSpy.mock.calls.some(([filters]) => (
      isExactKey(filters, CAPABILITIES_RUNTIME_QUERY_KEY)
    ))).toBe(false);
    expect(removeSpy.mock.calls.some(([filters]) => (
      isExactKey(filters, CAPABILITIES_RUNTIME_QUERY_KEY)
    ))).toBe(false);
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(getModelsMock).toHaveBeenCalledTimes(2);
  });

  it('never prefix-cancels or prefix-removes neighbor families', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });
    await waitFor(() => expect(result.current.capabilitiesLoading).toBe(false));
    await act(async () => {
      await result.current.reloadCapabilities();
      await result.current.reloadModels();
    });

    const allOps = [
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>;
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey.length === 1
      && filters.queryKey[0] === 'capabilities'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey.length === 1
      && filters.queryKey[0] === 'agent-models'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'settings'
    ))).toBe(false);
    assertExactRuntimeOps(allOps);
  });

  it('treats empty 200 items and empty models as success', async () => {
    listMock.mockResolvedValueOnce(capabilityResponse({
      items: [],
      total: 0,
      executable_count: 0,
      non_executable_count: 0,
      unknown_executable_count: 0,
    }));
    getModelsMock.mockResolvedValueOnce(modelResponse({ models: [] }));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });

    await waitFor(() => expect(result.current.capabilitiesLoading).toBe(false));
    await waitFor(() => expect(result.current.modelsLoading).toBe(false));
    expect(result.current.capabilities?.items).toEqual([]);
    expect(result.current.capabilities?.total).toBe(0);
    expect(result.current.models).toEqual([]);
    expect(result.current.capabilitiesError).toBeNull();
    expect(result.current.modelsError).toBeNull();
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });

    await waitFor(() => expect(result.current.capabilitiesLoading).toBe(false));
    await waitFor(() => expect(result.current.modelsLoading).toBe(false));
    expect(queryOptions(client, CAPABILITIES_RUNTIME_QUERY_KEY)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client, AGENT_MODELS_QUERY_KEY)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client, CAPABILITIES_RUNTIME_QUERY_KEY)?.retry).toBe(false);
    expect(queryOptions(client, CAPABILITIES_RUNTIME_QUERY_KEY)?.staleTime).toBe(0);
    expect(queryOptions(client, AGENT_MODELS_QUERY_KEY)?.networkMode).toBe('always');
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(getModelsMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(listMock).toHaveBeenCalledTimes(1);
    expect(getModelsMock).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call either GET again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });
    await waitFor(() => expect(result.current.capabilitiesLoading).toBe(false));
    expect(queryOptions(client, CAPABILITIES_RUNTIME_QUERY_KEY)?.refetchInterval).toBeUndefined();
    expect(queryOptions(client, AGENT_MODELS_QUERY_KEY)?.refetchInterval).toBeUndefined();

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
    expect(getModelsMock).toHaveBeenCalledTimes(1);
  });

  it('issues both GETs while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useRuntimeCapabilitiesQuery(), { wrapper });

    await waitFor(() => expect(result.current.capabilitiesLoading).toBe(false));
    await waitFor(() => expect(result.current.modelsLoading).toBe(false));
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(getModelsMock).toHaveBeenCalledTimes(1);
    expect(queryOptions(client, CAPABILITIES_RUNTIME_QUERY_KEY)?.networkMode).toBe('always');
    expect(queryOptions(client, AGENT_MODELS_QUERY_KEY)?.networkMode).toBe('always');
    expect(result.current.capabilities?.total).toBe(1);
    expect(result.current.models).toHaveLength(1);
  });
});
