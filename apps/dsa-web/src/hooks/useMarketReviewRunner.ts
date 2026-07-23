// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useRef, useState } from 'react';
import { analysisApi } from '../api/analysis';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import type { HistoryListResponse } from '../types/analysis';

export type MarketReviewNotice = {
  variant: 'success' | 'warning' | 'danger';
  title: string;
  message: string;
} | null;

type UseMarketReviewRunnerOptions = {
  notify: boolean;
  refreshMarketReviewHistory: (silent?: boolean) => Promise<HistoryListResponse | null>;
  onPersistedReport: (recordId: number) => void;
  onFeedback?: () => void;
};

export const MARKET_REVIEW_POLL_MAX_ATTEMPTS = 120;
export const MARKET_REVIEW_POLL_INTERVAL_MS = 2_000;

export function useMarketReviewRunner({
  notify,
  refreshMarketReviewHistory,
  onPersistedReport,
  onFeedback,
}: UseMarketReviewRunnerOptions) {
  const { t } = useUiLanguage();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [notice, setNotice] = useState<MarketReviewNotice>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const pollGenerationRef = useRef(0);
  const activeRef = useRef(true);
  const onPersistedReportRef = useRef(onPersistedReport);
  const onFeedbackRef = useRef(onFeedback);
  onPersistedReportRef.current = onPersistedReport;
  onFeedbackRef.current = onFeedback;

  const stopPolling = useCallback(() => {
    pollGenerationRef.current += 1;
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const clear = useCallback(() => {
    stopPolling();
    setNotice(null);
    setError(null);
  }, [stopPolling]);

  useEffect(() => {
    activeRef.current = true;
    return () => {
      activeRef.current = false;
      stopPolling();
    };
  }, [stopPolling]);

  const pollStatus = useCallback(async (taskId: string) => {
    stopPolling();
    const generation = pollGenerationRef.current;
    const isCurrent = () => (
      activeRef.current && generation === pollGenerationRef.current
    );
    let attempts = 0;

    const poll = async (): Promise<boolean> => {
      if (!isCurrent()) return false;
      if (attempts >= MARKET_REVIEW_POLL_MAX_ATTEMPTS) {
        setNotice({
          variant: 'danger',
          title: t('home.marketReviewTimeout'),
          message: t('home.marketReviewTimeoutMessage'),
        });
        onFeedbackRef.current?.();
        return false;
      }

      attempts += 1;
      try {
        const status = await analysisApi.getStatus(taskId);
        if (!isCurrent()) return false;

        if (status.status === 'pending' || status.status === 'processing') {
          const progress = typeof status.progress === 'number'
            ? `${status.progress}%`
            : t('home.progressActive');
          setNotice({
            variant: 'warning',
            title: t('home.marketReviewInProgress'),
            message: t('home.taskStatus', { status: status.status, progress }),
          });
          return true;
        }

        if (status.status === 'completed') {
          const refreshedHistory = await refreshMarketReviewHistory(true);
          if (!isCurrent()) return false;
          const persistedItem = refreshedHistory?.items.find((item) => (
            item.reportType === 'market_review' && item.queryId === taskId
          ));
          setNotice({
            variant: 'success',
            title: t('home.marketReviewCompleted'),
            message: persistedItem
              ? t('home.marketReviewCompletedWithReport')
              : t('home.marketReviewCompletedWithoutReport'),
          });
          setError(null);
          if (persistedItem) onPersistedReportRef.current(persistedItem.id);
          onFeedbackRef.current?.();
          return false;
        }

        if (status.status === 'failed') {
          setError(getParsedApiError({
            response: {
              status: 500,
              data: {
                error: 'market_review_failed',
                message: status.error || t('home.marketReviewFailed'),
              },
            },
          }));
          setNotice(null);
          onFeedbackRef.current?.();
          return false;
        }

        setNotice({
          variant: 'danger',
          title: t('home.marketReviewUnknownStatus'),
          message: t('home.unknownTaskStatus', { status: status.status }),
        });
        onFeedbackRef.current?.();
        return false;
      } catch (pollError: unknown) {
        if (!isCurrent()) return false;
        if (attempts >= MARKET_REVIEW_POLL_MAX_ATTEMPTS) {
          setError(getParsedApiError(pollError));
          setNotice(null);
          onFeedbackRef.current?.();
          return false;
        }
        return true;
      }
    };

    const runPoll = async (): Promise<void> => {
      const shouldContinue = await poll();
      if (!isCurrent() || !shouldContinue) return;
      pollTimerRef.current = window.setTimeout(() => {
        void runPoll();
      }, MARKET_REVIEW_POLL_INTERVAL_MS);
    };

    await runPoll();
  }, [refreshMarketReviewHistory, stopPolling, t]);

  const triggerMarketReview = useCallback(async () => {
    setIsSubmitting(true);
    setNotice(null);
    setError(null);
    onFeedbackRef.current?.();
    try {
      const result = await analysisApi.triggerMarketReview({ sendNotification: notify });
      if (!activeRef.current) return;
      setNotice({
        variant: 'success',
        title: t('home.marketReviewSubmitted'),
        message: result.message,
      });
      onFeedbackRef.current?.();
      if (result.taskId) void pollStatus(result.taskId);
    } catch (triggerError: unknown) {
      if (!activeRef.current) return;
      setError(getParsedApiError(triggerError));
      setNotice(null);
      onFeedbackRef.current?.();
    } finally {
      if (activeRef.current) setIsSubmitting(false);
    }
  }, [notify, pollStatus, t]);

  return {
    clear,
    dismissError: () => setError(null),
    error,
    isSubmitting,
    notice,
    triggerMarketReview,
  };
}

export default useMarketReviewRunner;
