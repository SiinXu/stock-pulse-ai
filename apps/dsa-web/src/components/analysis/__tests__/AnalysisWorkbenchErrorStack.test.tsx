// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ComponentProps } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { createParsedApiError } from '../../../api/error';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import AnalysisWorkbenchErrorStack from '../AnalysisWorkbenchErrorStack';

function renderStack(
  override: Partial<ComponentProps<typeof AnalysisWorkbenchErrorStack>> = {},
) {
  const onViewTasks = vi.fn();
  const onRetryAnalysis = vi.fn();
  const onClearError = vi.fn();
  render(
    <MemoryRouter>
      <UiLanguageProvider initialLanguage="zh">
        <AnalysisWorkbenchErrorStack
          inputError={undefined}
          duplicateError={null}
          duplicateTask={null}
          analysisError={null}
          reportDetailError={null}
          runFlowError={null}
          batchNotice={null}
          isAnalyzing={false}
          isBatchSubmitting={false}
          onClearError={onClearError}
          onClearRunFlowError={vi.fn()}
          onClearBatchNotice={vi.fn()}
          onFocusInput={vi.fn()}
          onRetryAnalysis={onRetryAnalysis}
          onRetryReportDetail={vi.fn()}
          onRetryRunFlow={vi.fn()}
          onRetryBatch={vi.fn()}
          onViewTasks={onViewTasks}
          {...override}
        />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
  return { onViewTasks, onRetryAnalysis, onClearError };
}

describe('AnalysisWorkbenchErrorStack busy recovery', () => {
  it('attaches duplicate_task through the shared assistant', () => {
    const { onViewTasks, onRetryAnalysis } = renderStack({
      analysisError: createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'duplicate_task',
        status: 409,
        params: { existing_task_id: 'task-dup' },
      }),
    });
    const alert = screen.getByTestId('actionable-api-error-inline');
    expect(alert).toHaveAttribute('data-error-class', 'busy');
    fireEvent.click(within(alert).getByRole('button', { name: '运行中任务' }));
    expect(onViewTasks).toHaveBeenCalledOnce();
    expect(onRetryAnalysis).not.toHaveBeenCalled();
    expect(within(alert).queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
  });

  it('keeps scheduler_busy on wait-and-dismiss without inventing retry or attach', () => {
    const { onViewTasks, onRetryAnalysis } = renderStack({
      analysisError: createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'scheduler_busy',
        status: 409,
      }),
    });
    const alert = screen.getByTestId('actionable-api-error-inline');
    expect(within(alert).queryByRole('button', { name: '运行中任务' })).not.toBeInTheDocument();
    expect(within(alert).queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
    fireEvent.click(within(alert).getByRole('button', { name: '关闭' }));
    expect(onViewTasks).not.toHaveBeenCalled();
    expect(onRetryAnalysis).not.toHaveBeenCalled();
  });

  it('retries portfolio_busy as the same operation', () => {
    const { onRetryAnalysis, onViewTasks } = renderStack({
      analysisError: createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'portfolio_busy',
        status: 409,
      }),
    });
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(onRetryAnalysis).toHaveBeenCalledOnce();
    expect(onViewTasks).not.toHaveBeenCalled();
  });

  it('does not apply busy recovery to a validation error', () => {
    const { onViewTasks, onRetryAnalysis } = renderStack({
      analysisError: createParsedApiError({
        title: 'invalid',
        message: 'invalid',
        code: 'validation_error',
        status: 422,
      }),
    });
    expect(screen.queryByRole('button', { name: '运行中任务' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
    expect(onViewTasks).not.toHaveBeenCalled();
    expect(onRetryAnalysis).not.toHaveBeenCalled();
  });
});
