// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import {
  useUnreadNotifications,
  type UnreadNotificationsState,
} from '../../../hooks/useUnreadNotifications';
import type { NotificationInboxItem } from '../../../types/notificationInbox';
import { NotificationBell } from '../NotificationBell';

vi.mock('../../../hooks/useUnreadNotifications', () => ({
  useUnreadNotifications: vi.fn(),
}));

const markAllSeen = vi.fn().mockResolvedValue(undefined);
const refresh = vi.fn();

const ITEM: NotificationInboxItem = {
  id: 'v1:alert_triggered:9:1786320000000000',
  kind: 'alert_triggered',
  titleKey: 'alertTriggeredTitle',
  titleParams: { target: 'MSFT' },
  summary: 'Price crossed threshold',
  severity: 'warning',
  createdAt: '2026-08-10T00:00:00Z',
  isRead: false,
  href: '/signals?tab=history&trigger=9',
  sourceId: '9',
};

function notificationState(
  overrides: Partial<UnreadNotificationsState> = {},
): UnreadNotificationsState {
  return {
    items: [],
    unreadCount: 0,
    isLoading: false,
    hasError: false,
    hasPartialError: false,
    listFailed: false,
    countFailed: false,
    markFailed: false,
    markAllSeen,
    refresh,
    ...overrides,
  };
}

function renderBell() {
  return render(
    <MemoryRouter>
      <UiLanguageProvider initialLanguage="zh">
        <NotificationBell />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
}

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    markAllSeen.mockResolvedValue(undefined);
    vi.mocked(useUnreadNotifications).mockReturnValue(notificationState());
  });

  it('marks the server inbox read and links to the shared inbox surface', async () => {
    vi.mocked(useUnreadNotifications).mockReturnValue(notificationState({
      items: [ITEM],
      unreadCount: 2,
    }));

    renderBell();
    fireEvent.click(screen.getByRole('button', { name: '通知，2 条未读' }));

    await waitFor(() => expect(markAllSeen).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('link', { name: /MSFT/ })).toHaveAttribute(
      'href',
      '/signals?tab=history&trigger=9',
    );
    expect(screen.getByRole('link', { name: '查看全部' })).toHaveAttribute(
      'href',
      '/notifications',
    );
  });

  it('keeps partial source degradation retryable', async () => {
    vi.mocked(useUnreadNotifications).mockReturnValue(notificationState({
      items: [ITEM],
      hasPartialError: true,
    }));
    renderBell();

    fireEvent.click(screen.getByRole('button', { name: '通知' }));

    expect(await screen.findByRole('status')).toHaveTextContent('部分通知暂时无法加载');
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('does not present cached rows as current when both inbox reads fail', async () => {
    vi.mocked(useUnreadNotifications).mockReturnValue(notificationState({
      items: [ITEM],
      hasError: true,
      listFailed: true,
      countFailed: true,
    }));
    renderBell();

    fireEvent.click(screen.getByRole('button', { name: '通知' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('暂时无法加载通知');
    expect(screen.queryByRole('link', { name: /MSFT/ })).not.toBeInTheDocument();
  });

  it('marks items after an open Bell finishes loading', async () => {
    vi.mocked(useUnreadNotifications)
      .mockReturnValueOnce(notificationState({ isLoading: true }))
      .mockReturnValue(notificationState({ items: [ITEM], unreadCount: 1 }));
    const view = renderBell();
    fireEvent.click(screen.getByRole('button', { name: '通知' }));

    view.rerender(
      <MemoryRouter>
        <UiLanguageProvider initialLanguage="zh">
          <NotificationBell />
        </UiLanguageProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(markAllSeen).toHaveBeenCalledTimes(1));
  });

  it('caps the visual badge without changing the accessible unread count', () => {
    vi.mocked(useUnreadNotifications).mockReturnValue(notificationState({ unreadCount: 125 }));
    renderBell();

    expect(screen.getByTestId('notification-unread-badge')).toHaveTextContent('99+');
    expect(screen.getByRole('button', { name: '通知，125 条未读' })).toBeInTheDocument();
  });
});
