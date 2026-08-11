// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect } from 'react';
import type { ParsedApiError } from '../api/error';
import { useToast } from '../components/common/toastContext';
import { mapApiErrorToActionable } from '../utils/apiReasonMapper';

export function useAnalysisErrorToast(
  error: ParsedApiError | null,
  clearError: () => void,
): boolean {
  const { showToast } = useToast();
  const isToastOnly = Boolean(error && mapApiErrorToActionable(error).class === 'generic');

  useEffect(() => {
    if (!error || !isToastOnly) return;
    showToast({
      title: error.title,
      message: error.traceId ? `${error.message} · trace: ${error.traceId}` : error.message,
      tone: 'danger',
      durationMs: 8000,
    });
    clearError();
  }, [clearError, error, isToastOnly, showToast]);

  return isToastOnly;
}
