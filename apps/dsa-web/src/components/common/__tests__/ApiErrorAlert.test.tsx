// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiErrorAlert } from '../ApiErrorAlert';

describe('ApiErrorAlert', () => {
  it('uses a compact Toast with shared controls and expandable diagnostics', () => {
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
    const details = screen.getByText(/^(?:查看详情|View details)$/);
    expect(screen.getByText('provider connection refused')).not.toBeVisible();

    fireEvent.click(retry);
    expect(onAction).toHaveBeenCalledTimes(1);
    fireEvent.click(details);
    expect(screen.getByText('provider connection refused')).toBeVisible();
    fireEvent.click(dismiss);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
