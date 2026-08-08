// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ComponentProps } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { createParsedApiError } from '../../../api/error';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ActionableApiErrorInline } from '../ActionableApiErrorInline';

function renderInline(
  error: ReturnType<typeof createParsedApiError>,
  props: Partial<ComponentProps<typeof ActionableApiErrorInline>> = {},
) {
  return render(
    <MemoryRouter>
      <UiLanguageProvider initialLanguage="zh">
        <ActionableApiErrorInline error={error} {...props} />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
}

describe('ActionableApiErrorInline', () => {
  it('renders llm_not_configured with settings CTA and collapsible technical code', () => {
    const error = createParsedApiError({
      title: 'llm',
      message: 'llm',
      code: 'llm_not_configured',
      category: 'llm_not_configured',
      status: 422,
    });
    renderInline(error);

    expect(screen.getByTestId('actionable-api-error-inline')).toHaveAttribute(
      'data-error-class',
      'llm_not_configured',
    );
    expect(screen.getByText('尚未配置 LLM 模型')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '去配置' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '查看详情' }));
    expect(screen.getByTestId('actionable-error-technical')).toHaveTextContent('code: llm_not_configured');
  });

  it('renders busy/duplicate with tasks CTA when preferTasksCta is set', () => {
    const onViewTasks = vi.fn();
    const error = createParsedApiError({
      title: 'busy',
      message: 'busy',
      code: 'duplicate_task',
      status: 409,
      params: { stock_code: 'AAPL' },
    });
    renderInline(error, { preferTasksCta: true, onViewTasks });

    expect(screen.getByTestId('actionable-api-error-inline')).toHaveAttribute(
      'data-error-class',
      'busy',
    );
    fireEvent.click(screen.getByRole('button', { name: '运行中任务' }));
    expect(onViewTasks).toHaveBeenCalledOnce();
  });

  it('invokes onRetry for network errors', () => {
    const onRetry = vi.fn();
    const error = createParsedApiError({
      title: 'net',
      message: 'net',
      category: 'upstream_network',
      status: 503,
    });
    renderInline(error, { onRetry });

    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
