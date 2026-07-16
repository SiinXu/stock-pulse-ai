import { useCallback, useEffect, useRef, useState } from 'react';
import { systemConfigApi } from '../api/systemConfig';
import type { LlmConnectionFieldSchema, LlmProviderCatalogEntry } from '../types/systemConfig';

interface ProviderCatalogState {
  providers: LlmProviderCatalogEntry[];
  connectionFields?: LlmConnectionFieldSchema[];
  emptyApiKeyHosts: string[];
  isLoading: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Fetches the authoritative LLM provider catalog from the backend. This is the
 * single source of Provider identity/default/capability metadata. Dynamic
 * field requirements come from connectionFields when that property is present.
 */
export function useProviderCatalog(): ProviderCatalogState {
  const [providers, setProviders] = useState<LlmProviderCatalogEntry[]>([]);
  const [connectionFields, setConnectionFields] = useState<LlmConnectionFieldSchema[] | undefined>();
  const [emptyApiKeyHosts, setEmptyApiKeyHosts] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const requestGenerationRef = useRef(0);

  const reload = useCallback(() => {
    setIsLoading(true);
    setError(null);
    setReloadToken((token) => token + 1);
  }, []);

  useEffect(() => {
    const requestGeneration = requestGenerationRef.current + 1;
    requestGenerationRef.current = requestGeneration;
    const isLatestRequest = () => requestGenerationRef.current === requestGeneration;
    systemConfigApi
      .getLlmProviderCatalog()
      .then((response) => {
        if (!isLatestRequest()) {
          return;
        }
        setProviders(response.providers ?? []);
        setConnectionFields(response.connectionFields);
        setEmptyApiKeyHosts(response.emptyApiKeyHosts ?? []);
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        if (!isLatestRequest()) {
          return;
        }
        setError(err instanceof Error ? err.message : 'Failed to load provider catalog');
        setIsLoading(false);
      });
    return () => {
      if (isLatestRequest()) {
        requestGenerationRef.current += 1;
      }
    };
  }, [reloadToken]);

  return { providers, connectionFields, emptyApiKeyHosts, isLoading, error, reload };
}
