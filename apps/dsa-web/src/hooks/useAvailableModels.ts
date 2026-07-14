import { useCallback, useEffect, useRef, useState } from 'react';
import { systemConfigApi } from '../api/systemConfig';
import type { AvailableModelEntry } from '../types/systemConfig';

interface AvailableModelsState {
  models: AvailableModelEntry[];
  isLoading: boolean;
  /** Non-null when the last fetch failed — never silently folded into empty. */
  error: string | null;
  reload: () => void;
}

/**
 * Fetches the model routes declared by currently-enabled connections. The route
 * set is authoritative (matches backend validation), so model selectors offer a
 * display name and store the exact route without deriving it in the frontend.
 * Pass a `reloadKey` (e.g. the config version) to refetch after a save.
 *
 * A load failure surfaces as `error` (with an empty `models`), so callers can
 * distinguish "no models configured" from "failed to load" and offer a retry.
 */
export function useAvailableModels(reloadKey?: string | number): AvailableModelsState {
  const [models, setModels] = useState<AvailableModelEntry[]>([]);
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
      .getLlmAvailableModels()
      .then((response) => {
        if (!activeRef.current) {
          return;
        }
        setModels(response.models ?? []);
        setError(null);
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        if (!activeRef.current) {
          return;
        }
        // Do NOT fold the failure into an empty list — surface it so the UI can
        // distinguish "no models" from "load failed" and offer a retry.
        setModels([]);
        setError(err instanceof Error ? err.message : 'Failed to load available models');
        setIsLoading(false);
      });
    return () => {
      activeRef.current = false;
    };
  }, [reloadKey, reloadToken]);

  return { models, isLoading, error, reload };
}
