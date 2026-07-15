import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LlmProviderCatalogEntry } from '../../types/systemConfig';
import { useProviderCatalog } from '../useProviderCatalog';

const { getLlmProviderCatalog } = vi.hoisted(() => ({ getLlmProviderCatalog: vi.fn() }));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: { getLlmProviderCatalog: (...args: unknown[]) => getLlmProviderCatalog(...args) },
}));

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

function providerEntry(id: string): LlmProviderCatalogEntry {
  return {
    id,
    label: id,
    protocol: 'openai',
    defaultBaseUrl: '',
    capabilities: ['chat'],
    requiresApiKey: true,
    requiresBaseUrl: false,
    supportsDiscovery: true,
    isLocal: false,
    isCustom: false,
  };
}

describe('useProviderCatalog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads the provider catalog from the backend', async () => {
    getLlmProviderCatalog.mockResolvedValue({
      providers: [{ id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek' }],
    });
    const { result } = renderHook(() => useProviderCatalog());
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.providers).toHaveLength(1);
    expect(result.current.providers[0].id).toBe('deepseek');
    expect(result.current.error).toBeNull();
  });

  it('surfaces an error without throwing when the catalog request fails', async () => {
    getLlmProviderCatalog.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useProviderCatalog());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBe('boom');
    expect(result.current.providers).toEqual([]);
  });

  it('keeps the latest catalog when reload responses resolve out of order', async () => {
    const first = createDeferred<{ providers: LlmProviderCatalogEntry[] }>();
    const second = createDeferred<{ providers: LlmProviderCatalogEntry[] }>();
    getLlmProviderCatalog
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const { result } = renderHook(() => useProviderCatalog());

    await waitFor(() => expect(getLlmProviderCatalog).toHaveBeenCalledTimes(1));
    act(() => result.current.reload());
    await waitFor(() => expect(getLlmProviderCatalog).toHaveBeenCalledTimes(2));

    await act(async () => {
      second.resolve({ providers: [providerEntry('latest')] });
      await second.promise;
    });
    expect(result.current.providers[0]?.id).toBe('latest');

    await act(async () => {
      first.resolve({ providers: [providerEntry('stale')] });
      await first.promise;
    });
    expect(result.current.providers[0]?.id).toBe('latest');
  });

  it('retains a loaded catalog and marks it stale when refresh fails', async () => {
    getLlmProviderCatalog
      .mockResolvedValueOnce({ providers: [{ id: 'openai', label: 'OpenAI', protocol: 'openai' }] })
      .mockRejectedValueOnce(new Error('refresh failed'));
    const { result } = renderHook(() => useProviderCatalog());

    await waitFor(() => expect(result.current.providers).toHaveLength(1));
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.error).toBe('refresh failed'));

    expect(result.current.providers[0]?.id).toBe('openai');
    expect(result.current.isStale).toBe(true);
    expect(result.current.status).toBe('error');
  });
});
