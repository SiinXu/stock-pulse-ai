import { useCallback, useEffect, useState } from 'react';
import { systemConfigApi } from '../api/systemConfig';
import type { AvailableModelEntry } from '../types/systemConfig';
import { createRequestKey, useAsyncResource, type AsyncResourceStatus } from './useAsyncResource';

interface AvailableModelsState {
  models: AvailableModelEntry[];
  isLoading: boolean;
  isRefreshing: boolean;
  isStale: boolean;
  status: AsyncResourceStatus;
  /** Non-null when the last fetch failed — never silently folded into empty. */
  error: string | null;
  requestKey: string | null;
  updatedAt: number | null;
  reload: () => void;
}

/**
 * Fetches the model routes declared by currently-enabled connections. The route
 * set is authoritative (matches backend validation), so model selectors offer a
 * display name and store the exact route without deriving it in the frontend.
 * Pass a `reloadKey` (e.g. the config version) to refetch after a save.
 *
 * A first-load failure surfaces as `error` with an empty list. A failed refresh
 * preserves the last successful list and reports `isStale`, so callers can
 * distinguish empty, failed, refreshing, and stale states.
 */
export function useAvailableModels(reloadKey?: string | number): AvailableModelsState {
  const [reloadToken, setReloadToken] = useState(0);
  const [resource, requests] = useAsyncResource<AvailableModelEntry[], string>({
    initialData: [],
    isEmpty: (models) => models.length === 0,
  });

  const reload = useCallback(() => {
    setReloadToken((token) => token + 1);
  }, []);

  useEffect(() => {
    const request = requests.begin(
      createRequestKey('available-models', [reloadKey ?? null, reloadToken]),
      { retainData: true },
    );
    systemConfigApi
      .getLlmAvailableModels()
      .then((response) => {
        requests.resolve(request, response.models ?? []);
      })
      .catch((err: unknown) => {
        // Do NOT fold the failure into an empty list — surface it so the UI can
        // distinguish "no models" from "load failed" and offer a retry.
        requests.reject(request, err instanceof Error ? err.message : 'Failed to load available models');
      });
  }, [reloadKey, reloadToken, requests]);

  return {
    models: resource.data,
    isLoading: resource.status === 'idle' || resource.status === 'loading',
    isRefreshing: resource.status === 'refreshing',
    isStale: resource.status === 'error' && resource.updatedAt != null,
    status: resource.status,
    error: resource.error,
    requestKey: resource.requestKey,
    updatedAt: resource.updatedAt,
    reload,
  };
}
