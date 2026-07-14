import { useEffect, useRef, useState } from 'react';
import { systemConfigApi } from '../api/systemConfig';
import type { AvailableModelEntry } from '../types/systemConfig';

/**
 * Fetches the model routes declared by currently-enabled connections. The route
 * set is authoritative (matches backend validation), so model selectors offer a
 * display name and store the exact route without deriving it in the frontend.
 * Pass a `reloadKey` (e.g. the config version) to refetch after a save.
 */
export function useAvailableModels(reloadKey?: string | number): {
  models: AvailableModelEntry[];
  isLoading: boolean;
} {
  const [models, setModels] = useState<AvailableModelEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const activeRef = useRef(true);

  useEffect(() => {
    activeRef.current = true;
    systemConfigApi
      .getLlmAvailableModels()
      .then((response) => {
        if (activeRef.current) {
          setModels(response.models ?? []);
          setIsLoading(false);
        }
      })
      .catch(() => {
        if (activeRef.current) {
          setModels([]);
          setIsLoading(false);
        }
      });
    return () => {
      activeRef.current = false;
    };
  }, [reloadKey]);

  return { models, isLoading };
}
