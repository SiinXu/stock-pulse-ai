// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect } from 'react';
import type { ParsedApiError } from '../api/error';
import { useToast } from '../contexts/ToastContext';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { mapApiErrorToActionable } from '../utils/apiReasonMapper';

export function useAnalysisErrorToast(
  error: ParsedApiError | null,
  clearError: () => void,
): boolean {
  const { showToast } = useToast();
  const { t } = useUiLanguage();
  const isToastOnly = Boolean(error && mapApiErrorToActionable(error).class === 'generic');

  useEffect(() => {
    if (!error || !isToastOnly) return;
    showToast({
      title: error.title,
      message: error.traceId
        ? `${error.message} · ${t('common.traceId', { id: error.traceId })}`
        : error.message,
      tone: 'danger',
      durationMs: 8000,
    });
    clearError();
  }, [clearError, error, isToastOnly, showToast, t]);

  return isToastOnly;
}
