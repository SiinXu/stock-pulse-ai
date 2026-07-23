import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useWatchlist } from '../useWatchlist';

const {
  mockGetWatchlist,
  mockAddToWatchlist,
  mockRemoveFromWatchlist,
} = vi.hoisted(() => ({
  mockGetWatchlist: vi.fn(),
  mockAddToWatchlist: vi.fn(),
  mockRemoveFromWatchlist: vi.fn(),
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getWatchlist: mockGetWatchlist,
    addToWatchlist: mockAddToWatchlist,
    removeFromWatchlist: mockRemoveFromWatchlist,
  },
}));

function deferredPromise<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, reject, resolve };
}

describe('useWatchlist', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetWatchlist.mockResolvedValue([]);
    mockAddToWatchlist.mockResolvedValue([]);
    mockRemoveFromWatchlist.mockResolvedValue([]);
  });

  it('defers the initial request until the consumer enables watchlist scope', async () => {
    mockGetWatchlist.mockResolvedValue(['AAPL']);
    const { result, rerender } = renderHook(
      ({ enabled }) => useWatchlist({ enabled }),
      { initialProps: { enabled: false } },
    );

    expect(result.current.isLoading).toBe(false);
    expect(mockGetWatchlist).not.toHaveBeenCalled();

    rerender({ enabled: true });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockGetWatchlist).toHaveBeenCalledOnce();
    expect(result.current.watchlistCodes).toEqual(['AAPL']);
  });

  it('keeps the newest watchlist result when an older refresh resolves last', async () => {
    const older = deferredPromise<string[]>();
    const newer = deferredPromise<string[]>();
    mockGetWatchlist
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);
    const { result, rerender } = renderHook(
      ({ enabled }) => useWatchlist({ enabled }),
      { initialProps: { enabled: true } },
    );

    await waitFor(() => expect(mockGetWatchlist).toHaveBeenCalledTimes(1));
    rerender({ enabled: false });
    rerender({ enabled: true });
    await waitFor(() => expect(mockGetWatchlist).toHaveBeenCalledTimes(2));

    await act(async () => newer.resolve(['NEW']));
    await waitFor(() => expect(result.current.watchlistCodes).toEqual(['NEW']));
    await act(async () => older.resolve(['OLD']));

    expect(result.current.watchlistCodes).toEqual(['NEW']);
    expect(result.current.loadError).toBeNull();
    expect(result.current.isLoading).toBe(false);
  });

  it('ignores an older watchlist error after a newer refresh succeeds', async () => {
    const older = deferredPromise<string[]>();
    const newer = deferredPromise<string[]>();
    mockGetWatchlist
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);
    const { result, rerender } = renderHook(
      ({ enabled }) => useWatchlist({ enabled }),
      { initialProps: { enabled: true } },
    );

    await waitFor(() => expect(mockGetWatchlist).toHaveBeenCalledTimes(1));
    rerender({ enabled: false });
    rerender({ enabled: true });
    await waitFor(() => expect(mockGetWatchlist).toHaveBeenCalledTimes(2));

    await act(async () => newer.resolve(['NEW']));
    await waitFor(() => expect(result.current.watchlistCodes).toEqual(['NEW']));
    await act(async () => older.reject(new Error('stale watchlist failure')));

    expect(result.current.watchlistCodes).toEqual(['NEW']);
    expect(result.current.loadError).toBeNull();
    expect(result.current.isLoading).toBe(false);
  });

  it('matches raw HK watchlist entries against prefixed and suffixed variants', async () => {
    mockGetWatchlist.mockResolvedValue(['00700']);

    const { result } = renderHook(() => useWatchlist());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isInWatchlist('00700')).toBe(true);
    expect(result.current.isInWatchlist('HK00700')).toBe(true);
    expect(result.current.isInWatchlist('00700.HK')).toBe(true);
    expect(result.current.isInWatchlist('HK01810')).toBe(false);
  });

  it('removes the matched raw watchlist entry instead of adding a duplicate variant', async () => {
    mockGetWatchlist.mockResolvedValue(['00700']);
    mockRemoveFromWatchlist.mockResolvedValue([]);

    const { result } = renderHook(() => useWatchlist());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    await act(async () => {
      await result.current.toggleWatchlist('HK00700');
    });

    expect(mockRemoveFromWatchlist).toHaveBeenCalledWith('00700');
    expect(mockAddToWatchlist).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(result.current.watchlistCodes).toEqual([]);
    });
  });

  it('compares submitted and stored US tickers case-insensitively', async () => {
    mockGetWatchlist.mockResolvedValue(['aapl']);
    mockRemoveFromWatchlist.mockResolvedValue([]);

    const { result } = renderHook(() => useWatchlist());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isInWatchlist('AAPL')).toBe(true);

    await act(async () => {
      await result.current.toggleWatchlist('AAPL');
    });

    expect(mockRemoveFromWatchlist).toHaveBeenCalledWith('aapl');
    expect(mockAddToWatchlist).not.toHaveBeenCalled();
  });
});
