import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

export type AsyncResourceStatus =
  | 'idle'
  | 'loading'
  | 'refreshing'
  | 'success'
  | 'empty'
  | 'error';

export interface AsyncResourceState<T, E = unknown> {
  data: T;
  status: AsyncResourceStatus;
  error: E | null;
  requestKey: string | null;
  updatedAt: number | null;
}

export interface AsyncResourceRequest {
  generation: number;
  requestKey: string;
}

interface UseAsyncResourceOptions<T> {
  initialData: T;
  isEmpty: (data: T) => boolean;
}

interface BeginRequestOptions {
  retainData: boolean;
}

export interface AsyncResourceController<T, E = unknown> {
  begin: (requestKey: string, options: BeginRequestOptions) => AsyncResourceRequest;
  resolve: (request: AsyncResourceRequest, data: T) => boolean;
  reject: (request: AsyncResourceRequest, error: E) => boolean;
  isCurrent: (request: AsyncResourceRequest) => boolean;
  clearError: () => void;
  reset: () => void;
}

/**
 * Keeps async resource state and request ownership together. Every completion
 * must present the token returned by begin(), so stale and post-unmount
 * responses are ignored without relying on each component to repeat guards.
 */
export function useAsyncResource<T, E = unknown>({
  initialData,
  isEmpty,
}: UseAsyncResourceOptions<T>): [AsyncResourceState<T, E>, AsyncResourceController<T, E>] {
  const initialDataRef = useRef(initialData);
  const isEmptyRef = useRef(isEmpty);
  const [state, setState] = useState<AsyncResourceState<T, E>>(() => ({
    data: initialData,
    status: 'idle',
    error: null,
    requestKey: null,
    updatedAt: null,
  }));
  const stateRef = useRef(state);
  const generationRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    isEmptyRef.current = isEmpty;
  }, [isEmpty]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
    };
  }, []);

  const commit = useCallback((nextState: AsyncResourceState<T, E>) => {
    stateRef.current = nextState;
    if (mountedRef.current) {
      setState(nextState);
    }
  }, []);

  const isCurrent = useCallback((request: AsyncResourceRequest) => (
    mountedRef.current
    && generationRef.current === request.generation
    && stateRef.current.requestKey === request.requestKey
  ), []);

  const begin = useCallback((requestKey: string, options: BeginRequestOptions) => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    const current = stateRef.current;
    const retainData = options.retainData && !isEmptyRef.current(current.data);
    commit({
      data: retainData ? current.data : initialDataRef.current,
      status: retainData ? 'refreshing' : 'loading',
      error: null,
      requestKey,
      updatedAt: retainData ? current.updatedAt : null,
    });
    return { generation, requestKey };
  }, [commit]);

  const resolve = useCallback((request: AsyncResourceRequest, data: T) => {
    if (!isCurrent(request)) {
      return false;
    }
    commit({
      data,
      status: isEmptyRef.current(data) ? 'empty' : 'success',
      error: null,
      requestKey: request.requestKey,
      updatedAt: Math.max(Date.now(), (stateRef.current.updatedAt ?? 0) + 1),
    });
    return true;
  }, [commit, isCurrent]);

  const reject = useCallback((request: AsyncResourceRequest, error: E) => {
    if (!isCurrent(request)) {
      return false;
    }
    commit({
      ...stateRef.current,
      status: 'error',
      error,
      requestKey: request.requestKey,
    });
    return true;
  }, [commit, isCurrent]);

  const clearError = useCallback(() => {
    const current = stateRef.current;
    if (current.status !== 'error') {
      return;
    }
    commit({
      ...current,
      status: isEmptyRef.current(current.data) ? 'empty' : 'success',
      error: null,
    });
  }, [commit]);

  const reset = useCallback(() => {
    generationRef.current += 1;
    commit({
      data: initialDataRef.current,
      status: 'idle',
      error: null,
      requestKey: null,
      updatedAt: null,
    });
  }, [commit]);

  const controller = useMemo(
    () => ({ begin, resolve, reject, isCurrent, clearError, reset }),
    [begin, clearError, isCurrent, reject, reset, resolve],
  );

  return [state, controller];
}

export function createRequestKey(namespace: string, parts: readonly unknown[]): string {
  return `${namespace}:${JSON.stringify(parts)}`;
}
