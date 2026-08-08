// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import type { ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { useStockPoolStore } from '../../stores/stockPoolStore';
import {
  isBusyParsedApiError,
} from '../../utils/apiReasonMapper';
import { InlineAlert } from '../common';
import { ActionableApiErrorInline } from './ActionableApiErrorInline';

export type WorkbenchBatchNotice = {
  variant: 'success' | 'warning' | 'danger';
  message: string;
  error?: ParsedApiError;
} | null;

export interface AnalysisWorkbenchErrorStackProps {
  inputError?: string;
  duplicateError: ParsedApiError | null;
  duplicateTask: { stockCode: string; existingTaskId: string } | null;
  visibleError: ParsedApiError | null;
  deleteError: ParsedApiError | null;
  isDeleteConfirmOpen: boolean;
  runFlowError: ParsedApiError | null;
  batchNotice: WorkbenchBatchNotice;
  onClearError: () => void;
  onClearDeleteError: () => void;
  onClearRunFlowError: () => void;
  onClearBatchNotice: () => void;
  onViewTasks: () => void;
}

/**
 * Analysis Workbench error stack: form-primary actionable alerts (#885 Phase 2).
 * Keeps toast dual-feedback out of launch/batch/run-flow failure paths.
 */
export const AnalysisWorkbenchErrorStack: React.FC<AnalysisWorkbenchErrorStackProps> = ({
  inputError,
  duplicateError,
  duplicateTask,
  visibleError,
  deleteError,
  isDeleteConfirmOpen,
  runFlowError,
  batchNotice,
  onClearError,
  onClearDeleteError,
  onClearRunFlowError,
  onClearBatchNotice,
  onViewTasks,
}) => {
  const { t } = useUiLanguage();

  return (
    <div className="mt-4 space-y-3" aria-live="polite">
      {inputError ? (
        <InlineAlert variant="danger" title={t('home.inputInvalid')} message={inputError} />
      ) : null}
      {duplicateError ? (
        <ActionableApiErrorInline
          error={duplicateError}
          titleOverride={t('home.duplicateTask')}
          messageOverride={duplicateTask
            ? t('home.duplicateTaskMessage', { stock: duplicateTask.stockCode })
            : undefined}
          preferTasksCta
          onViewTasks={onViewTasks}
          onDismiss={() => {
            useStockPoolStore.getState().clearInlineMessages();
          }}
        />
      ) : null}
      {visibleError ? (
        <ActionableApiErrorInline
          error={visibleError}
          onDismiss={onClearError}
          preferTasksCta={isBusyParsedApiError(visibleError)}
          onViewTasks={onViewTasks}
          onRetry={onClearError}
        />
      ) : null}
      {deleteError && !isDeleteConfirmOpen ? (
        <ActionableApiErrorInline
          error={deleteError}
          onDismiss={onClearDeleteError}
          onRetry={onClearDeleteError}
        />
      ) : null}
      {runFlowError ? (
        <ActionableApiErrorInline
          error={runFlowError}
          onDismiss={onClearRunFlowError}
          onRetry={onClearRunFlowError}
        />
      ) : null}
      {batchNotice?.error && batchNotice.variant === 'danger' ? (
        <ActionableApiErrorInline
          error={batchNotice.error}
          messageOverride={batchNotice.message}
          onDismiss={onClearBatchNotice}
          preferTasksCta={isBusyParsedApiError(batchNotice.error)}
          onViewTasks={onViewTasks}
          onRetry={onClearBatchNotice}
        />
      ) : batchNotice ? (
        <InlineAlert
          variant={batchNotice.variant}
          message={batchNotice.message}
        />
      ) : null}
    </div>
  );
};

export default AnalysisWorkbenchErrorStack;
