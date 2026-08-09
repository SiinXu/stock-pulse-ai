// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import type { ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import { useStockPoolStore } from '../../stores/stockPoolStore';
import { mapApiErrorToActionable } from '../../utils/apiReasonMapper';
import { Button, InlineAlert } from '../common';
import ActionableApiErrorInline, {
  type ActionableApiErrorAction,
} from './ActionableApiErrorInline';

export type WorkbenchBatchNotice = {
  variant: 'success' | 'warning' | 'danger';
  message: string;
  error?: ParsedApiError;
  confirmedCodes?: readonly string[];
  unconfirmedCodes?: readonly string[];
  canRetryUnconfirmed?: boolean;
} | null;

export interface AnalysisWorkbenchErrorStackProps {
  inputError?: string;
  duplicateError: ParsedApiError | null;
  duplicateTask: { stockCode: string; existingTaskId: string } | null;
  analysisError: ParsedApiError | null;
  reportDetailError: ParsedApiError | null;
  runFlowError: ParsedApiError | null;
  batchNotice: WorkbenchBatchNotice;
  isAnalyzing: boolean;
  isBatchSubmitting: boolean;
  onClearError: () => void;
  onClearRunFlowError: () => void;
  onClearBatchNotice: () => void;
  onFocusInput: () => void;
  onRetryAnalysis: () => void;
  onRetryReportDetail: () => void;
  onRetryRunFlow: () => void;
  onRetryBatch: () => void;
  onViewTasks: () => void;
}

const RETRYABLE_CLASSES = new Set(['network', 'rate_quota']);

/**
 * Analysis Workbench error stack: operation owners explicitly supply every
 * recovery action. The renderer never turns descriptive mappings into retries.
 */
const AnalysisWorkbenchErrorStack: React.FC<AnalysisWorkbenchErrorStackProps> = ({
  inputError,
  duplicateError,
  duplicateTask,
  analysisError,
  reportDetailError,
  runFlowError,
  batchNotice,
  isAnalyzing,
  isBatchSubmitting,
  onClearError,
  onClearRunFlowError,
  onClearBatchNotice,
  onFocusInput,
  onRetryAnalysis,
  onRetryReportDetail,
  onRetryRunFlow,
  onRetryBatch,
  onViewTasks,
}) => {
  const { t } = useUiLanguage();

  const contextualAction = (error: ParsedApiError): ActionableApiErrorAction | null => {
    const mapping = mapApiErrorToActionable(error);
    if (mapping.class === 'auth' && mapping.cta?.target === APP_ROUTE_PATHS.login) {
      return { label: t('login.adminLogin'), target: APP_ROUTE_PATHS.login };
    }
    if (mapping.cta?.kind === 'navigate' && mapping.cta.target) {
      return {
        label: mapping.cta.target.startsWith(APP_ROUTE_PATHS.settings)
          ? t('home.goSettings')
          : t('common.details'),
        target: mapping.cta.target,
      };
    }
    if (mapping.class === 'config_conflict' && mapping.cta?.kind === 'reload') {
      return { label: t('routeError.reload'), reload: true };
    }
    if (mapping.class === 'validation') {
      return { label: t('home.inputInvalid'), onClick: onFocusInput };
    }
    return null;
  };

  const operationActions = (
    error: ParsedApiError,
    retry: () => void,
    loading = false,
  ): ActionableApiErrorAction[] => {
    const mapping = mapApiErrorToActionable(error);
    if (mapping.class === 'busy') {
      return [{ label: t('analysisWorkbench.tasks'), onClick: onViewTasks }];
    }
    const contextual = contextualAction(error);
    if (contextual) return [contextual];
    if (!RETRYABLE_CLASSES.has(mapping.class)) return [];
    return [{
      label: t('common.retry'),
      onClick: retry,
      disabled: loading,
      isLoading: loading,
    }];
  };

  const batchActions = batchNotice?.error ? (() => {
    const actions: ActionableApiErrorAction[] = [];
    const mapping = mapApiErrorToActionable(batchNotice.error);
    if (
      (batchNotice.confirmedCodes?.length ?? 0) > 0
      || mapping.class === 'busy'
    ) {
      actions.push({ label: t('analysisWorkbench.tasks'), onClick: onViewTasks });
    }
    const contextual = contextualAction(batchNotice.error);
    if (contextual) actions.push(contextual);
    if (
      (RETRYABLE_CLASSES.has(mapping.class) || batchNotice.canRetryUnconfirmed)
      && (batchNotice.unconfirmedCodes?.length ?? 0) > 0
    ) {
      actions.push({
        label: t('common.retry'),
        onClick: onRetryBatch,
        disabled: isBatchSubmitting,
        isLoading: isBatchSubmitting,
      });
    }
    return actions;
  })() : [];

  return (
    <div className="mt-4 space-y-3" aria-live="polite">
      {inputError ? (
        <InlineAlert
          variant="danger"
          title={t('home.inputInvalid')}
          message={inputError}
          action={(
            <Button type="button" variant="secondary" size="compact" onClick={onFocusInput}>
              {t('home.inputInvalid')}
            </Button>
          )}
        />
      ) : null}
      {duplicateError ? (
        <ActionableApiErrorInline
          error={duplicateError}
          titleOverride={t('home.duplicateTask')}
          messageOverride={duplicateTask
            ? t('home.duplicateTaskMessage', { stock: duplicateTask.stockCode })
            : undefined}
          actions={[{ label: t('analysisWorkbench.tasks'), onClick: onViewTasks }]}
          onDismiss={() => useStockPoolStore.getState().clearInlineMessages()}
        />
      ) : null}
      {reportDetailError ? (
        <ActionableApiErrorInline
          error={reportDetailError}
          actions={operationActions(reportDetailError, onRetryReportDetail)}
          onDismiss={onClearError}
        />
      ) : analysisError ? (
        <ActionableApiErrorInline
          error={analysisError}
          actions={operationActions(analysisError, onRetryAnalysis, isAnalyzing)}
          onDismiss={onClearError}
        />
      ) : null}
      {runFlowError ? (
        <ActionableApiErrorInline
          error={runFlowError}
          actions={operationActions(runFlowError, onRetryRunFlow)}
          onDismiss={onClearRunFlowError}
        />
      ) : null}
      {batchNotice?.error ? (
        <ActionableApiErrorInline
          error={batchNotice.error}
          messageOverride={batchNotice.message}
          actions={batchActions}
          onDismiss={onClearBatchNotice}
        />
      ) : batchNotice ? (
        <InlineAlert variant={batchNotice.variant} message={batchNotice.message} />
      ) : null}
    </div>
  );
};

export default AnalysisWorkbenchErrorStack;
