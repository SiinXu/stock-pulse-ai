import { useCallback, useEffect, useRef, useState } from 'react';
import { systemConfigApi } from '../api/systemConfig';
import type { LlmProviderCatalogEntry } from '../types/systemConfig';

interface ProviderCatalogState {
  providers: LlmProviderCatalogEntry[];
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
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const activeRef = useRef(true);

  const reload = useCallback(() => {
    setIsLoading(true);
    setError(null);
    setReloadToken((token) => token + 1);
  }, []);

  useEffect(() => {
    activeRef.current = true;
    systemConfigApi
      .getLlmProviderCatalog()
      .then((response) => {
        if (!activeRef.current) {
          return;
        }
        setProviders(response.providers ?? []);
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        if (!activeRef.current) {
          return;
        }
        setError(err instanceof Error ? err.message : 'Failed to load provider catalog');
        setIsLoading(false);
      });
    return () => {
      activeRef.current = false;
    };
  }, [reloadToken]);

  return { providers, isLoading, error, reload };
}
