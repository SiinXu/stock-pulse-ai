// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ComponentProps } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { createParsedApiError } from '../../../api/error';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import ActionableApiErrorInline from '../ActionableApiErrorInline';

function renderInline(
  error: ReturnType<typeof createParsedApiError>,
  props: Partial<ComponentProps<typeof ActionableApiErrorInline>> = {},
  initialEntry = '/research/analysis?segment=history#report',
) {
  const LocationProbe = () => {
    const location = useLocation();
    return <span data-testid="location">{`${location.pathname}${location.search}`}</span>;
  };
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="*" element={(
          <UiLanguageProvider initialLanguage="zh">
            <ActionableApiErrorInline error={error} {...props} />
            <LocationProbe />
          </UiLanguageProvider>
        )} />
      </Routes>
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
    renderInline(error, {
      actions: [{ label: '去配置', target: '/settings?section=ai-models' }],
    });

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
    renderInline(error, {
      actions: [{ label: '运行中任务', onClick: onViewTasks }],
    });

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
    renderInline(error, {
      actions: [{ label: '重试', onClick: onRetry }],
    });

    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it.each([
    { code: 'validation_error', status: 422 },
    { code: 'not_found', status: 404 },
    { code: 'unknown_code', status: 500 },
  ])('does not invent a retry action for $code', ({ code, status }) => {
    const error = createParsedApiError({
      title: 'invalid',
      message: 'invalid',
      code,
      status,
    });
    renderInline(error);

    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
  });

  it('uses an admin-login label and preserves a safe return route', () => {
    const error = createParsedApiError({
      title: 'auth',
      message: 'auth',
      code: 'unauthorized',
      status: 401,
    });
    renderInline(error, {
      actions: [{ label: '管理员登录', target: '/login' }],
    });

    fireEvent.click(screen.getByRole('button', { name: '管理员登录' }));
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/login?redirect=%2Fresearch%2Fanalysis%3Fsegment%3Dhistory%23report',
    );
  });

  it('redacts unsafe technical values and never discloses response details', () => {
    const error = createParsedApiError({
      title: 'network',
      message: 'network',
      code: 'network_error',
      category: 'upstream_network',
      status: 503,
      traceId: 'trace-safe',
      details: {
        reason: 'sk-super-secret',
        authorization: 'Basic hidden',
        response_body: 'private payload',
      },
    });
    renderInline(error);

    fireEvent.click(screen.getByRole('button', { name: '查看详情' }));
    const technical = screen.getByTestId('actionable-error-technical');
    expect(technical).toHaveTextContent('reason: [redacted]');
    expect(technical).toHaveTextContent('trace: trace-safe');
    expect(technical).not.toHaveTextContent('super-secret');
    expect(technical).not.toHaveTextContent('private payload');
    expect(technical).not.toHaveTextContent('Basic hidden');
  });
});
