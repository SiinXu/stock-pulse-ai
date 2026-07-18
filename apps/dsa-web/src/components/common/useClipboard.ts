import { useCallback, useState } from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

export function useClipboard() {
  const { t } = useUiLanguage();
  const [copyError, setCopyError] = useState<string | null>(null);

  const copyText = useCallback(async (value: string): Promise<boolean> => {
    setCopyError(null);
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error('Clipboard API unavailable');
      }
      await navigator.clipboard.writeText(value);
      return true;
    } catch (error) {
      console.error('Copy failed:', error);
      setCopyError(t('common.copyFailed'));
      return false;
    }
  }, [t]);

  return {
    copyText,
    copyError,
    clearCopyError: () => setCopyError(null),
  };
}
