import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../api/history';
import { agentApi } from '../../../api/agent';
import type { StockIndexItem } from '../../../types/stockIndex';
import { resetStockIndexCacheForTests } from '../../../utils/stockIndexLoader';
import { STOCK_SEARCH_MIN_LENGTH, useCommandPaletteSearch } from '../useCommandPaletteSearch';

vi.mock('../../../api/history', () => ({
  historyApi: { search: vi.fn() },
}));

vi.mock('../../../api/agent', () => ({
  agentApi: { getSkills: vi.fn() },
}));

const searchHistory = vi.mocked(historyApi.search);
const getSkills = vi.mocked(agentApi.getSkills);

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

function mockStockIndexFetch(data: StockIndexItem[] = mockIndex) {
  let parseCount = 0;
  const fetchMock = vi.fn(async () => ({
    ok: true,
    json: async () => {
      parseCount += 1;
      return data;
    },
  }));
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, getParseCount: () => parseCount };
}

describe('useCommandPaletteSearch stock index loading', () => {
  beforeEach(() => {
    resetStockIndexCacheForTests();
    searchHistory.mockResolvedValue({ query: '', limit: 5, items: [] });
    getSkills.mockResolvedValue({ skills: [], default_skill_id: '' });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    resetStockIndexCacheForTests();
  });

  it('does not fetch the stock index while the palette is closed', () => {
    const { fetchMock } = mockStockIndexFetch();

    renderHook(() => useCommandPaletteSearch('茅台', false));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('fetches once when the palette opens even if search remounts', async () => {
    const { fetchMock, getParseCount } = mockStockIndexFetch();

    const { rerender } = renderHook(
      ({ isOpen }) => useCommandPaletteSearch('', isOpen),
      { initialProps: { isOpen: false } },
    );

    expect(fetchMock).not.toHaveBeenCalled();

    rerender({ isOpen: true });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    rerender({ isOpen: true });
    rerender({ isOpen: false });
    rerender({ isOpen: true });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(getParseCount()).toBe(1);
    expect(fetchMock).toHaveBeenCalledWith('/stocks.index.json');
  });

  it('surfaces a stock-index failure when the user searches stocks', async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error('Network error');
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const { result, rerender } = renderHook(
      ({ query, isOpen }) => useCommandPaletteSearch(query, isOpen),
      { initialProps: { query: '', isOpen: true } },
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(result.current.hasError).toBe(false);

    rerender({ query: '茅'.repeat(STOCK_SEARCH_MIN_LENGTH), isOpen: true });

    await waitFor(() => expect(result.current.hasError).toBe(true));
    expect(result.current.stocks).toEqual([]);
  });

  it('opens twice rapidly against an in-flight load without a second fetch', async () => {
    let resolveJson: ((value: StockIndexItem[]) => void) | undefined;
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: () => new Promise<StockIndexItem[]>((resolve) => {
        resolveJson = resolve;
      }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    const { rerender } = renderHook(
      ({ isOpen }) => useCommandPaletteSearch('', isOpen),
      { initialProps: { isOpen: false } },
    );

    rerender({ isOpen: true });
    rerender({ isOpen: false });
    rerender({ isOpen: true });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await act(async () => {
      resolveJson?.(mockIndex);
    });
  });
});
