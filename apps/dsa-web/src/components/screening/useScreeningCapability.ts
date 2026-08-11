import { useCallback, useEffect, useRef, useState } from 'react';
import { alphasiftApi } from '../../api/alphasift';
import { getParsedApiError } from '../../api/error';
import type { UiLanguage } from '../../i18n/uiText';
import type { ScreeningCapability } from './screeningPageState';
import { getScreeningCapabilityState } from './screeningPageState';

type UseScreeningCapabilityArgs = {
  language: UiLanguage;
  enableFailedText: string;
  loadStrategies: () => Promise<void>;
  loadHotspots: (refresh?: boolean) => Promise<void>;
};

export function useScreeningCapability({
  language,
  enableFailedText,
  loadStrategies,
  loadHotspots,
}: UseScreeningCapabilityArgs) {
  const mountedRef = useRef(true);
  const [capability, setCapability] = useState<ScreeningCapability>({
    state: 'loading',
    error: null,
  });
  const [enabling, setEnabling] = useState(false);
  const [actionError, setActionError] = useState('');

  const loadStatus = useCallback(async () => {
    setCapability({ state: 'loading', error: null });
    setActionError('');
    try {
      const status = await alphasiftApi.getStatus();
      if (!mountedRef.current) return;
      const state = getScreeningCapabilityState({
        statusLoading: false,
        statusError: null,
        enabled: status.enabled,
        available: status.available,
      });
      setCapability({ state, error: null });
      if (state === 'ready') {
        void loadStrategies();
        void loadHotspots(false);
      }
    } catch (statusError) {
      if (!mountedRef.current) return;
      const parsed = getParsedApiError(statusError, language);
      setCapability({ state: 'status_error', error: parsed });
    }
  }, [language, loadHotspots, loadStrategies]);

  const enable = useCallback(async () => {
    setEnabling(true);
    setActionError('');
    try {
      await alphasiftApi.enable();
      if (!mountedRef.current) return;
      setCapability({ state: 'ready', error: null });
      await loadStrategies();
    } catch (enableError) {
      try {
        const status = await alphasiftApi.getStatus();
        if (!mountedRef.current) return;
        setCapability({
          state: getScreeningCapabilityState({
            statusLoading: false,
            statusError: null,
            enabled: status.enabled,
            available: status.available,
          }),
          error: null,
        });
      } catch (statusError) {
        if (!mountedRef.current) return;
        const parsed = getParsedApiError(statusError, language);
        setCapability({ state: 'status_error', error: parsed });
      }
      if (mountedRef.current) {
        setActionError(getParsedApiError(enableError, language).message || enableFailedText);
      }
    } finally {
      if (mountedRef.current) setEnabling(false);
    }
  }, [enableFailedText, language, loadStrategies]);

  useEffect(() => {
    mountedRef.current = true;
    void loadStatus();
    return () => {
      mountedRef.current = false;
    };
  }, [loadStatus]);

  return {
    capability,
    enabling,
    actionError,
    loadStatus,
    enable,
  };
}
