import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAvailableModels } from '../useAvailableModels';

const { getLlmAvailableModels } = vi.hoisted(() => ({
  getLlmAvailableModels: vi.fn(),
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getLlmAvailableModels: (...args: unknown[]) => getLlmAvailableModels(...args),
  },
}));

function modelEntry(route: string) {
  return {
    modelRef: `modelref:v1:openai:${encodeURIComponent(route)}`,
    route,
    display: route.split('/').pop() || route,
    connection: 'openai',
    connectionId: 'openai',
    connectionName: 'openai',
    provider: 'openai',
    providerId: 'openai',
    providerLabel: 'OpenAI 官方',
    available: true,
  };
}

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

describe('useAvailableModels', () => {
  beforeEach(() => {
    getLlmAvailableModels.mockReset();
  });

  it('exposes the fetched models with no error on success', async () => {
    getLlmAvailableModels.mockResolvedValue({ models: [modelEntry('openai/gpt-4o-mini')] });
    const { result } = renderHook(() => useAvailableModels());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.models).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('treats an empty catalog as an empty (not failed) state', async () => {
    getLlmAvailableModels.mockResolvedValue({ models: [] });
    const { result } = renderHook(() => useAvailableModels());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.models).toEqual([]);
    // Empty is NOT an error: the UI shows an actionable empty state, not a failure.
    expect(result.current.error).toBeNull();
  });

  it('surfaces a load failure as an error distinct from an empty catalog', async () => {
    getLlmAvailableModels.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useAvailableModels());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.models).toEqual([]);
    // A failure must NOT be folded into an empty list — it carries an error.
    expect(result.current.error).toBe('boom');
  });

  it('recovers via reload() after a failure', async () => {
    getLlmAvailableModels.mockRejectedValueOnce(new Error('boom'));
    getLlmAvailableModels.mockResolvedValueOnce({ models: [modelEntry('openai/gpt-4o-mini')] });
    const { result } = renderHook(() => useAvailableModels());

    await waitFor(() => expect(result.current.error).toBe('boom'));

    act(() => result.current.reload());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.models).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('does not let an older request overwrite a newer reload result', async () => {
    const first = createDeferred<{ models: ReturnType<typeof modelEntry>[] }>();
    const second = createDeferred<{ models: ReturnType<typeof modelEntry>[] }>();
    getLlmAvailableModels
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const { result } = renderHook(() => useAvailableModels());

    await waitFor(() => expect(getLlmAvailableModels).toHaveBeenCalledTimes(1));
    act(() => result.current.reload());
    await waitFor(() => expect(getLlmAvailableModels).toHaveBeenCalledTimes(2));

    await act(async () => {
      second.resolve({ models: [modelEntry('openai/new-model')] });
      await second.promise;
    });
    expect(result.current.models[0]?.route).toBe('openai/new-model');

    await act(async () => {
      first.resolve({ models: [modelEntry('openai/stale-model')] });
      await first.promise;
    });
    expect(result.current.models[0]?.route).toBe('openai/new-model');
  });
});
