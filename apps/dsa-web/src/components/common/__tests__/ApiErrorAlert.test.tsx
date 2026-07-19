// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiErrorAlert } from '../ApiErrorAlert';

describe('ApiErrorAlert', () => {
  it('uses shared controls for dismiss and retry while preserving disclosure behavior', () => {
    const onAction = vi.fn();
    const onDismiss = vi.fn();
    render(
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
      />,
    );

    const dismiss = screen.getByRole('button', { name: 'Dismiss' });
    const retry = screen.getByRole('button', { name: 'Retry' });
    const summary = screen.getByText(/^(?:查看详情|View details)$/);

    expect(dismiss).toHaveAttribute('data-control', 'icon-button');
    expect(dismiss).toHaveAttribute('data-size', 'compact');
    expect(retry).toHaveAttribute('data-control', 'button');
    expect(retry).toHaveAttribute('data-variant', 'danger-subtle');
    expect(retry).toHaveAttribute('data-size', 'compact');

    fireEvent.click(dismiss);
    fireEvent.click(retry);
    fireEvent.click(summary);
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(summary.closest('details')).toHaveAttribute('open');
  });
});
