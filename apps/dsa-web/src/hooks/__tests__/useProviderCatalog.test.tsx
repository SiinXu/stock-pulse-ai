import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useProviderCatalog } from '../useProviderCatalog';

const { getLlmProviderCatalog } = vi.hoisted(() => ({ getLlmProviderCatalog: vi.fn() }));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: { getLlmProviderCatalog: (...args: unknown[]) => getLlmProviderCatalog(...args) },
}));

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
});
