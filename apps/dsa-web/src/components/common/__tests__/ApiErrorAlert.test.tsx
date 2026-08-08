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

  it('renders catalog remediation action and hint for high-impact codes', () => {
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

    expect(screen.getByRole('button', { name: /打开模型设置|Open model settings/ })).toBeInTheDocument();
    expect(screen.getByText(/模型接入|Model Access/)).toBeInTheDocument();
    expect(screen.getByText(/LLM API Key missing diagnostic/)).toBeInTheDocument();
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
    expect(screen.queryByRole('button', { name: /Open Agent settings|打开 Agent 设置/ })).not.toBeInTheDocument();
  });
});
