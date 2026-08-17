import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { StockIndexItem } from '../../types/stockIndex';
import { createDeferred } from '../../test-utils';
import { resetStockIndexCacheForTests } from '../../utils/stockIndexLoader';
import { useStockIndex } from '../useStockIndex';

const mockIndex: StockIndexItem[] = [
  {
    canonicalCode: '600519.SH',
    displayCode: '600519',
    nameZh: '贵州茅台',
    pinyinFull: 'guizhoumaotai',
    pinyinAbbr: 'gzmt',
    aliases: ['茅台'],
    market: 'CN',
    assetType: 'stock',
    active: true,
    popularity: 100,
  },
];

function mockStockIndexResponse(data: StockIndexItem[] = mockIndex) {
  let parseCount = 0;
  const fetchMock = vi.fn(async () => ({
    ok: true,
    json: async () => {
      parseCount += 1;
      return data;
    },
  }));
  vi.stubGlobal('fetch', fetchMock);
  return {
    fetchMock,
    getParseCount: () => parseCount,
  };
}

describe('useStockIndex', () => {
  beforeEach(() => {
    resetStockIndexCacheForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    resetStockIndexCacheForTests();
  });

  it('does not fetch when enabled is false', () => {
    const { fetchMock } = mockStockIndexResponse();

    const { result } = renderHook(() => useStockIndex({ enabled: false }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
    expect(result.current.loaded).toBe(false);
    expect(result.current.index).toEqual([]);
  });

  it('fetches on mount when enabled defaults to true', async () => {
    const { fetchMock, getParseCount } = mockStockIndexResponse();

    const { result } = renderHook(() => useStockIndex());

    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith('/stocks.index.json');
    expect(getParseCount()).toBe(1);
    expect(result.current.index).toEqual(mockIndex);
    expect(result.current.fallback).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('starts the fetch when enabled flips from false to true', async () => {
    const { fetchMock } = mockStockIndexResponse();

    const { result, rerender } = renderHook(
      ({ enabled }) => useStockIndex({ enabled }),
      { initialProps: { enabled: false } },
    );

    expect(fetchMock).not.toHaveBeenCalled();

    rerender({ enabled: true });

    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.index).toEqual(mockIndex);
  });

  it('shares one fetch and one parse across mounted consumers', async () => {
    const deferred = createDeferred<StockIndexItem[]>();
    let parseCount = 0;
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => {
        parseCount += 1;
        return deferred.promise;
      },
    }));
    vi.stubGlobal('fetch', fetchMock);

    function useTwoConsumers() {
      return [useStockIndex(), useStockIndex()] as const;
    }

    const { result } = renderHook(() => useTwoConsumers());

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current[0].loading).toBe(true);
    expect(result.current[1].loading).toBe(true);

    deferred.resolve(mockIndex);

    await waitFor(() => {
      expect(result.current[0].loaded).toBe(true);
      expect(result.current[1].loaded).toBe(true);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(parseCount).toBe(1);
    expect(result.current[0].index).toBe(result.current[1].index);
  });

  it('surfaces a failed fetch as error plus fallback instead of a silent empty index', async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error('Network error');
    });
    vi.stubGlobal('fetch', fetchMock);
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const { result } = renderHook(() => useStockIndex());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.fallback).toBe(true);
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.index).toEqual([]);
    expect(result.current.loaded).toBe(true);
    expect(consoleError).toHaveBeenCalled();
  });
});
