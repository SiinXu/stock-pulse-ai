import { useCallback, useEffect, useRef, useState } from 'react';
import { systemConfigApi } from '../api/systemConfig';
import type { LlmProviderCatalogEntry } from '../types/systemConfig';

interface ProviderCatalogState {
  providers: LlmProviderCatalogEntry[];
  emptyApiKeyHosts: string[];
  isLoading: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Fetches the authoritative LLM provider catalog from the backend. This is the
 * single business source of truth for provider metadata (labels, protocol,
 * default endpoint, credential/base-URL requirements, capabilities) — the Web
 * must not maintain a second hardcoded list.
 */
export function useProviderCatalog(): ProviderCatalogState {
  const [providers, setProviders] = useState<LlmProviderCatalogEntry[]>([]);
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

  return { providers, emptyApiKeyHosts, isLoading, error, reload };
}
