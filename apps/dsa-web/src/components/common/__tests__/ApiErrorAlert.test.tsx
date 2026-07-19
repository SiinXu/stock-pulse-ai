// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiErrorAlert } from '../ApiErrorAlert';

describe('ApiErrorAlert', () => {
  it('keeps compact icon, disclosure, and action targets accessible', () => {
    render(
      <ApiErrorAlert
        error={{
          title: 'Request failed',
          message: 'Try again.',
          rawMessage: 'provider connection refused',
          category: 'upstream_network',
        }}
        actionLabel="Retry"
        onAction={vi.fn()}
        dismissLabel="Dismiss"
        onDismiss={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'Dismiss' })).toHaveClass('ui-touch-target', 'h-6', 'w-6');
    expect(screen.queryByText('Dismiss')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toHaveClass('ui-touch-target', 'h-6', 'min-w-6');
    expect(screen.getByText(/^(?:查看详情|View details)$/)).toHaveClass('min-h-11');
  });
});
