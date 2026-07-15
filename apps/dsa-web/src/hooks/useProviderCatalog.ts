import { useCallback, useEffect, useState } from 'react';
import { systemConfigApi } from '../api/systemConfig';
import type { LlmProviderCatalogEntry } from '../types/systemConfig';
import { createRequestKey, useAsyncResource, type AsyncResourceStatus } from './useAsyncResource';

interface ProviderCatalogData {
  providers: LlmProviderCatalogEntry[];
  emptyApiKeyHosts: string[];
}

const EMPTY_PROVIDER_CATALOG: ProviderCatalogData = {
  providers: [],
  emptyApiKeyHosts: [],
};

interface ProviderCatalogState {
  providers: LlmProviderCatalogEntry[];
  emptyApiKeyHosts: string[];
  isLoading: boolean;
  isRefreshing: boolean;
  isStale: boolean;
  status: AsyncResourceStatus;
  error: string | null;
  requestKey: string | null;
  updatedAt: number | null;
  reload: () => void;
}

/**
 * Fetches the authoritative LLM provider catalog from the backend. This is the
 * single business source of truth for provider metadata (labels, protocol,
 * default endpoint, credential/base-URL requirements, capabilities) — the Web
 * must not maintain a second hardcoded list.
 */
export function useProviderCatalog(): ProviderCatalogState {
  const [reloadToken, setReloadToken] = useState(0);
  const [resource, requests] = useAsyncResource<ProviderCatalogData, string>({
    initialData: EMPTY_PROVIDER_CATALOG,
    isEmpty: (data) => data.providers.length === 0,
  });

  const reload = useCallback(() => {
    setReloadToken((token) => token + 1);
  }, []);

  useEffect(() => {
    const request = requests.begin(
      createRequestKey('provider-catalog', [reloadToken]),
      { retainData: true },
    );
    systemConfigApi
      .getLlmProviderCatalog()
      .then((response) => {
        requests.resolve(request, {
          providers: response.providers ?? [],
          emptyApiKeyHosts: response.emptyApiKeyHosts ?? [],
        });
      })
      .catch((err: unknown) => {
        requests.reject(request, err instanceof Error ? err.message : 'Failed to load provider catalog');
      });
  }, [reloadToken, requests]);

  return {
    providers: resource.data.providers,
    emptyApiKeyHosts: resource.data.emptyApiKeyHosts,
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
