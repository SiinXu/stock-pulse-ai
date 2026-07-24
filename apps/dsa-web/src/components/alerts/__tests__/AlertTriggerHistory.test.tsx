// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { AlertTriggerItem } from '../../../types/alerts';
import { AlertTriggerHistory } from '../AlertTriggerHistory';

const triggers: AlertTriggerItem[] = [{
  id: 42,
  ruleId: 1,
  target: 'AAPL',
  status: 'triggered',
  reason: 'Price crossed threshold',
  triggeredAt: '2026-07-23T10:00:00Z',
}];

describe('AlertTriggerHistory', () => {
  const scrollIntoView = vi.fn();

  beforeEach(() => {
    scrollIntoView.mockClear();
    HTMLElement.prototype.scrollIntoView = scrollIntoView;
  });

  it('highlights, focuses, and scrolls the deep-linked trigger row', async () => {
    render(
      <UiLanguageProvider initialLanguage="en">
        <AlertTriggerHistory triggers={triggers} selectedTriggerId={42} />
      </UiLanguageProvider>,
    );

    const row = screen.getByTestId('alert-trigger-row-42');
    expect(row).toHaveAttribute('aria-selected', 'true');
    expect(row).toHaveAttribute('data-row-selected', 'true');
    await waitFor(() => expect(screen.getByText('AAPL')).toHaveFocus());
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center' });
  });
});
