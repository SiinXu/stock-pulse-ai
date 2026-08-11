import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useWatchlistGroups } from '../useWatchlistGroups';
import { createDeferred } from '../../test-utils';
import type { WatchlistGroupState } from '../../types/watchlist';

const { mockList, mockCreate } = vi.hoisted(() => ({
  mockList: vi.fn(),
  mockCreate: vi.fn(),
}));

vi.mock('../../api/watchlistGroups', () => ({
  watchlistGroupsApi: {
    list: mockList,
    create: mockCreate,
    remove: vi.fn(),
    reorderGroups: vi.fn(),
    reorderMembers: vi.fn(),
    moveMember: vi.fn(),
  },
}));

const state = (revision: number): WatchlistGroupState => ({ revision, groups: [] });

describe('useWatchlistGroups', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue(state(1));
  });

  it('acquires an action lease synchronously so same-render double submit runs once', async () => {
    const pending = createDeferred<WatchlistGroupState>();
    mockCreate.mockReturnValue(pending.promise);
    const { result } = renderHook(() => useWatchlistGroups());
    await waitFor(() => expect(result.current.revision).toBe(1));

    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    act(() => {
      first = result.current.createGroup('Core');
      second = result.current.createGroup('Duplicate');
    });
    expect(mockCreate).toHaveBeenCalledOnce();
    await expect(second).resolves.toBe(false);
    await act(async () => pending.resolve(state(2)));
    await expect(first).resolves.toBe(true);
    expect(result.current.revision).toBe(2);
  });

  it('does not let an older action response overwrite a newer refresh', async () => {
    const pendingAction = createDeferred<WatchlistGroupState>();
    const pendingRefresh = createDeferred<WatchlistGroupState>();
    mockCreate.mockReturnValue(pendingAction.promise);
    const { result } = renderHook(() => useWatchlistGroups());
    await waitFor(() => expect(result.current.revision).toBe(1));

    let action!: Promise<boolean>;
    act(() => { action = result.current.createGroup('Core'); });
    mockList.mockReturnValueOnce(pendingRefresh.promise);
    let refresh!: Promise<boolean>;
    act(() => { refresh = result.current.refresh(); });
    await act(async () => pendingRefresh.resolve(state(3)));
    await expect(refresh).resolves.toBe(true);
    await act(async () => pendingAction.resolve(state(2)));
    await expect(action).resolves.toBe(false);

    expect(result.current.revision).toBe(3);
    expect(result.current.isActioning).toBe(false);
  });

  it('returns false through the public callback when a mutation fails', async () => {
    mockCreate.mockRejectedValue(new Error('create failed'));
    const { result } = renderHook(() => useWatchlistGroups());
    await waitFor(() => expect(result.current.revision).toBe(1));

    let succeeded!: boolean;
    await act(async () => {
      succeeded = await result.current.createGroup('Core');
    });

    expect(succeeded).toBe(false);
    expect(result.current.errorMessage).toBeTruthy();
    expect(mockList).toHaveBeenCalledTimes(2);
  });
});
