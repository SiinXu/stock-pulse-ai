// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { createParsedApiError } from '../../../api/error';
import { ApiErrorAlert } from '../ApiErrorAlert';

describe('ApiErrorAlert', () => {
  it('uses a compact Toast with shared dismiss and retry controls', () => {
    const onAction = vi.fn();
    const onDismiss = vi.fn();
    render(
      <div data-testid="page-layout">
        <ApiErrorAlert
          error={{
            title: 'Request failed',
            message: 'Try again.',
            rawMessage: 'provider connection refused',
            category: 'upstream_network',
          }}
          actionLabel="Retry"
          onAction={onAction}
          dismissLabel="Dismiss"
          onDismiss={onDismiss}
        />
      </div>,
    );

    const dismiss = screen.getByRole('button', { name: 'Dismiss' });
    const retry = screen.getByRole('button', { name: 'Retry' });

    expect(screen.getByTestId('page-layout')).toBeEmptyDOMElement();
    expect(dismiss.closest('[data-overlay-root="toast"]')).not.toBeNull();
    expect(dismiss).toHaveAttribute('data-control', 'icon-button');
    expect(dismiss).toHaveAttribute('data-size', 'compact');
    expect(retry).toHaveAttribute('data-control', 'button');
    expect(retry).toHaveAttribute('data-variant', 'ghost');
    expect(retry).toHaveAttribute('data-size', 'default');
    expect(screen.queryByText(/^(?:查看详情|View details)$/)).not.toBeInTheDocument();
    expect(screen.queryByText('provider connection refused')).not.toBeInTheDocument();

    fireEvent.click(retry);
    expect(onAction).toHaveBeenCalledTimes(1);
    fireEvent.click(dismiss);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('renders paired catalog remediation in the shared Toast without raw diagnostics', () => {
    render(
      <ApiErrorAlert
        error={createParsedApiError({
          title: '尚未配置 LLM 模型',
          message: '请在设置中配置主要模型、模型连接或 API Key。',
          rawMessage: 'LLM API Key missing diagnostic',
          category: 'llm_not_configured',
          code: 'llm_not_configured',
          status: 422,
        })}
      />,
    );

    const remediationAction = screen.getByRole('button', { name: /打开设置|Open Settings/ });
    expect(remediationAction.closest('[data-overlay-root="toast"]')).not.toBeNull();
    expect(screen.getByText(/主要模型|primary model/i)).toBeInTheDocument();
    expect(screen.queryByText(/LLM API Key missing diagnostic/)).not.toBeInTheDocument();
  });

  it('keeps catalog guidance without a destination from becoming a dead action', () => {
    render(
      <ApiErrorAlert
        error={createParsedApiError({
          title: 'Upstream timeout',
          message: 'Try again later.',
          category: 'upstream_timeout',
        })}
      />,
    );

    expect(screen.getByText('Try again later.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /重试|Retry/i })).not.toBeInTheDocument();
  });

  it('pairs a caller retry handler with the catalog retry label', () => {
    const onAction = vi.fn();
    render(
      <ApiErrorAlert
        error={createParsedApiError({
          title: 'Upstream timeout',
          message: 'Try again later.',
          category: 'upstream_timeout',
        })}
        onAction={onAction}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /重试|Retry/i }));
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it('does not combine an incomplete caller action with a catalog destination', () => {
    render(
      <ApiErrorAlert
        error={createParsedApiError({
          title: 'No model',
          message: 'Configure a model.',
          category: 'llm_not_configured',
          code: 'llm_not_configured',
        })}
        actionLabel="Custom action"
      />,
    );

    expect(screen.queryByRole('button', { name: 'Custom action' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /打开设置|Open Settings/ })).not.toBeInTheDocument();
    expect(screen.getByText(/主要模型|primary model/i)).toBeInTheDocument();
  });

  it('lets explicit action props override remediation navigation', () => {
    const onAction = vi.fn();
    render(
      <ApiErrorAlert
        error={createParsedApiError({
          title: 'Agent 模式未开启',
          message: '开启 Agent 模式后重试。',
          category: 'agent_disabled',
          code: 'agent_disabled',
        })}
        actionLabel="Custom retry"
        onAction={onAction}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Custom retry' }));
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: /Open Settings|打开设置/ })).not.toBeInTheDocument();
  });

  it('opens docs remediation in a new tab for docs-default taxonomy codes', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(
      <ApiErrorAlert
        error={createParsedApiError({
          title: 'Password cannot be changed here',
          message: 'This password source does not support changes from the Web app.',
          code: 'not_changeable',
          category: 'http_error',
        })}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Related docs|相关文档/i }));
    expect(openSpy).toHaveBeenCalledTimes(1);
    expect(String(openSpy.mock.calls[0]?.[0])).toContain('github.com/SiinXu/stock-pulse-ai');
    expect(openSpy.mock.calls[0]?.[1]).toBe('_blank');
    openSpy.mockRestore();
  });

  it('does not treat dismiss-only handlers as taxonomy retry without onAction', () => {
    render(
      <ApiErrorAlert
        error={createParsedApiError({
          title: 'Upstream timeout',
          message: 'Try again later.',
          category: 'upstream_timeout',
          code: 'upstream_timeout',
        })}
        onDismiss={() => undefined}
      />,
    );

    expect(screen.queryByRole('button', { name: /重试|Retry/i })).not.toBeInTheDocument();
  });

  it('maps taxonomy severity to toast tone', () => {
    const { unmount } = render(
      <ApiErrorAlert
        error={createParsedApiError({
          title: 'Too many attempts',
          message: 'Wait a moment.',
          code: 'rate_limited',
          category: 'http_error',
        })}
      />,
    );
    const warningError = screen.getByRole('alert');
    expect(warningError).toHaveAttribute('data-toast-tone', 'warning');
    unmount();

    render(
      <ApiErrorAlert
        error={createParsedApiError({
          title: 'Internal',
          message: 'Failed',
          code: 'internal_error',
          category: 'http_error',
        })}
      />,
    );
    expect(document.querySelector('[data-toast-tone="danger"]')).not.toBeNull();
  });

});
