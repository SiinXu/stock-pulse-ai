import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useAsyncResource } from '../useAsyncResource';

function renderStringResource() {
  return renderHook(() => useAsyncResource<string[], Error>({
    initialData: [],
    isEmpty: (items) => items.length === 0,
  }));
}

describe('useAsyncResource', () => {
  it('keeps loading, refreshing, empty, error, and success mutually exclusive', () => {
    const { result } = renderStringResource();
    let initialRequest!: ReturnType<typeof result.current[1]['begin']>;

    act(() => {
      initialRequest = result.current[1].begin('items:first', { retainData: false });
    });
    expect(result.current[0]).toMatchObject({
      data: [],
      status: 'loading',
      error: null,
      requestKey: 'items:first',
      updatedAt: null,
    });

    act(() => {
      result.current[1].resolve(initialRequest, []);
    });
    expect(result.current[0].status).toBe('empty');

    let populatedRequest!: ReturnType<typeof result.current[1]['begin']>;
    act(() => {
      populatedRequest = result.current[1].begin('items:populated', { retainData: false });
      result.current[1].resolve(populatedRequest, ['latest']);
    });
    expect(result.current[0]).toMatchObject({ data: ['latest'], status: 'success', error: null });
    expect(result.current[0].updatedAt).not.toBeNull();

    let refreshRequest!: ReturnType<typeof result.current[1]['begin']>;
    act(() => {
      refreshRequest = result.current[1].begin('items:refresh', { retainData: true });
    });
    expect(result.current[0]).toMatchObject({ data: ['latest'], status: 'refreshing', error: null });

    act(() => {
      result.current[1].reject(refreshRequest, new Error('refresh failed'));
    });
    expect(result.current[0].data).toEqual(['latest']);
    expect(result.current[0].status).toBe('error');
    expect(result.current[0].error?.message).toBe('refresh failed');
  });

  it('ignores stale completions and invalidates requests on unmount', () => {
    const { result, unmount } = renderStringResource();
    let first!: ReturnType<typeof result.current[1]['begin']>;
    let second!: ReturnType<typeof result.current[1]['begin']>;

    act(() => {
      first = result.current[1].begin('items:first', { retainData: false });
      second = result.current[1].begin('items:second', { retainData: false });
    });
    expect(result.current[1].resolve(first, ['stale'])).toBe(false);

    act(() => {
      expect(result.current[1].resolve(second, ['latest'])).toBe(true);
    });
    expect(result.current[0].data).toEqual(['latest']);

    let afterUnmount!: ReturnType<typeof result.current[1]['begin']>;
    act(() => {
      afterUnmount = result.current[1].begin('items:unmount', { retainData: true });
    });
    unmount();
    expect(result.current[1].resolve(afterUnmount, ['too late'])).toBe(false);
  });
});
