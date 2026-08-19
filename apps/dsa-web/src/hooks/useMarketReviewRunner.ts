// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useMutation } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { analysisApi } from '../api/analysis';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import type { HistoryListResponse, MarketReviewRegion } from '../types/analysis';
import {
  isActiveTaskStatus,
  isLaunchBlockingError,
  isTerminalTaskStatus,
  normalizeTaskProgress,
  resolveBusyRecoveryDecision,
} from '../utils/asyncTaskUx';
import {
  formatMarketReviewRegionLabels,
  MARKET_REVIEW_REGION_UI_TEXT_KEYS,
} from '../utils/marketReviewRegion';
import { formatTaskMessage } from '../utils/taskMessage';

export type MarketReviewNotice = {
  variant: 'success' | 'warning' | 'danger';
  title: string;
  message: string;
} | null;

type UseMarketReviewRunnerOptions = {
  notify: boolean;
  regions?: readonly MarketReviewRegion[];
  refreshMarketReviewHistory: (silent?: boolean) => Promise<HistoryListResponse | null>;
  onPersistedReport: (recordId: number) => void;
  onFeedback?: () => void;
};

export const MARKET_REVIEW_POLL_MAX_ATTEMPTS = 120;
export const MARKET_REVIEW_POLL_INTERVAL_MS = 2_000;

export function useMarketReviewRunner({
  notify,
  regions,
  refreshMarketReviewHistory,
  onPersistedReport,
  onFeedback,
}: UseMarketReviewRunnerOptions) {
  const { t, language } = useUiLanguage();
  const formatRegionToken = useCallback(
    (regionToken: string) => formatMarketReviewRegionLabels(
      regionToken,
      (region) => t(MARKET_REVIEW_REGION_UI_TEXT_KEYS[region]),
      language,
    ),
    [language, t],
  );
  const [notice, setNotice] = useState<MarketReviewNotice>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const pollGenerationRef = useRef(0);
  const activeRef = useRef(true);
  const onPersistedReportRef = useRef(onPersistedReport);
  const onFeedbackRef = useRef(onFeedback);

  useEffect(() => {
    onPersistedReportRef.current = onPersistedReport;
    onFeedbackRef.current = onFeedback;
  }, [onFeedback, onPersistedReport]);

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
    setActiveTaskId(null);
  }, [stopPolling]);

  useEffect(() => {
    activeRef.current = true;
    return () => {
      activeRef.current = false;
      stopPolling();
    };
  }, [stopPolling]);

  const buildActiveNoticeMessage = useCallback((status: {
    status?: string | null;
    progress?: number | null;
    region?: string | null;
    message?: string | null;
    messageCode?: string | null;
    messageParams?: Record<string, unknown> | null;
  }) => {
    const phaseMessage = formatTaskMessage({
      status: status.status,
      message: status.message,
      messageCode: status.messageCode,
      messageParams: status.messageParams,
    }, language);
    const progressPart = typeof status.progress === 'number'
      ? `${normalizeTaskProgress(status.progress)}%`
      : t('home.progressActive');
    const regionPart = status.region ? formatRegionToken(status.region) : '';
    return [phaseMessage, progressPart, regionPart].filter(Boolean).join(' · ');
  }, [formatRegionToken, language, t]);

  const pollStatus = useCallback(async (taskId: string) => {
    stopPolling();
    setActiveTaskId(taskId);
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
        setActiveTaskId(null);
        onFeedbackRef.current?.();
        return false;
      }

      attempts += 1;
      try {
        const status = await analysisApi.getStatus(taskId);
        if (!isCurrent()) return false;

        if (isActiveTaskStatus(status.status)) {
          setNotice({
            variant: 'warning',
            title: t('home.marketReviewInProgress'),
            message: buildActiveNoticeMessage(status),
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
          setActiveTaskId(null);
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
          setActiveTaskId(null);
          onFeedbackRef.current?.();
          return false;
        }

        if (isTerminalTaskStatus(status.status)) {
          setNotice({
            variant: 'warning',
            title: formatTaskMessage({ status: status.status }, language),
            message: formatTaskMessage({
              status: status.status,
              message: status.message,
              messageCode: status.messageCode,
              messageParams: status.messageParams,
            }, language),
          });
          setError(null);
          setActiveTaskId(null);
          onFeedbackRef.current?.();
          return false;
        }

        setNotice({
          variant: 'danger',
          title: t('home.marketReviewUnknownStatus'),
          message: t('home.unknownTaskStatus', { status: status.status }),
        });
        setActiveTaskId(null);
        onFeedbackRef.current?.();
        return false;
      } catch (pollError: unknown) {
        if (!isCurrent()) return false;
        if (attempts >= MARKET_REVIEW_POLL_MAX_ATTEMPTS) {
          setError(getParsedApiError(pollError));
          setNotice(null);
          setActiveTaskId(null);
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
  }, [buildActiveNoticeMessage, language, refreshMarketReviewHistory, stopPolling, t]);

  const triggerMutation = useMutation({
    mutationFn: () => analysisApi.triggerMarketReview({
      sendNotification: notify,
      regions,
    }),
    retry: false,
    onMutate: () => {
      setNotice(null);
      setError(null);
      setActiveTaskId(null);
      onFeedbackRef.current?.();
    },
    onSuccess: (result) => {
      if (!activeRef.current) return;
      setNotice({
        variant: 'success',
        title: t('home.marketReviewSubmitted'),
        message: t('home.marketReviewSubmittedWithRegion', {
          message: result.message,
          region: formatRegionToken(result.region),
        }),
      });
      onFeedbackRef.current?.();
      if (result.taskId) void pollStatus(result.taskId);
    },
    onError: (triggerError: unknown) => {
      if (!activeRef.current) return;
      const parsed = getParsedApiError(triggerError);
      const recovery = resolveBusyRecoveryDecision(parsed);
      if (recovery.kind === 'attach_or_view_tasks' && recovery.existingTaskId) {
        setError(null);
        setNotice({
          variant: 'warning',
          title: t('home.duplicateTask'),
          message: t('home.marketReviewInProgress'),
        });
        onFeedbackRef.current?.();
        void pollStatus(recovery.existingTaskId);
        return;
      }
      setError(parsed);
      setNotice(null);
      setActiveTaskId(null);
      onFeedbackRef.current?.();
    },
  });

  const triggerMarketReview = useCallback(async () => {
    try {
      await triggerMutation.mutateAsync();
    } catch {
      // Error surface is owned by onError + local error state.
    }
  }, [triggerMutation]);

  const isLaunchBlocked = useMemo(
    () => triggerMutation.isPending || isLaunchBlockingError(error) || Boolean(activeTaskId),
    [activeTaskId, error, triggerMutation.isPending],
  );

  return {
    activeTaskId,
    clear,
    dismissError: () => setError(null),
    error,
    isLaunchBlocked,
    isSubmitting: triggerMutation.isPending,
    notice,
    triggerMarketReview,
  };
}

export default useMarketReviewRunner;
