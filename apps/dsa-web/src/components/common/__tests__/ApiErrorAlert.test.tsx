// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiErrorAlert } from '../ApiErrorAlert';

describe('ApiErrorAlert', () => {
  it('keeps disclosure and action targets at least 44px', () => {
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

    expect(screen.getByRole('button', { name: 'Dismiss' })).toHaveClass('min-h-11', 'min-w-11');
    expect(screen.getByRole('button', { name: 'Retry' })).toHaveClass('min-h-11', 'min-w-11');
    expect(screen.getByText(/^(?:查看详情|View details)$/)).toHaveClass('min-h-11');
  });
});
