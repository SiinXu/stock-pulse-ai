// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { useUnreadNotifications } from '../../../hooks/useUnreadNotifications';
import type { UnreadNotificationsState } from '../../../hooks/useUnreadNotifications';
import { NotificationBell } from '../NotificationBell';

vi.mock('../../../hooks/useUnreadNotifications', () => ({
  useUnreadNotifications: vi.fn(),
}));

const markAllSeen = vi.fn();
const refresh = vi.fn();

function notificationState(
  overrides: Partial<UnreadNotificationsState> = {},
): UnreadNotificationsState {
  return {
    signalItems: [],
    alertItems: [],
    unreadSignalCount: 0,
    unreadAlertCount: 0,
    unreadCount: 0,
    isLoading: false,
    hasError: false,
    hasPartialError: false,
    signalsFailed: false,
    alertsFailed: false,
    signalLastSeenAt: 0,
    alertLastSeenAt: 0,
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
    vi.mocked(useUnreadNotifications).mockReturnValue(notificationState());
  });

  it('marks notifications seen on open and exposes grouped Signal Center deep links', async () => {
    vi.mocked(useUnreadNotifications).mockReturnValue(notificationState({
      signalItems: [{
        id: 7,
        stockCode: 'AAPL',
        stockName: 'Apple',
        market: 'us',
        sourceType: 'analysis',
        triggerSource: 'analysis',
        action: 'buy',
        actionLabel: 'Buy',
        planQuality: 'complete',
        status: 'active',
        createdAt: '2026-07-23T10:00:00Z',
      }],
      alertItems: [{
        id: 9,
        ruleId: 3,
        target: 'MSFT',
        status: 'triggered',
        reason: 'Price crossed threshold',
        triggeredAt: '2026-07-23T11:00:00Z',
      }],
      unreadSignalCount: 1,
      unreadAlertCount: 1,
      unreadCount: 2,
    }));

    renderBell();

    expect(screen.getByTestId('notification-unread-badge')).toHaveTextContent('2');
    fireEvent.click(screen.getByRole('button', { name: '通知，2 条未读' }));

    expect(markAllSeen).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole('dialog', { name: '通知' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '信号' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '告警' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Apple/ })).toHaveAttribute(
      'href',
      '/signals?stock=AAPL&signal=7',
    );
    expect(screen.getByRole('link', { name: /MSFT/ })).toHaveAttribute(
      'href',
      '/signals?tab=history&trigger=9',
    );
    expect(screen.getByRole('link', { name: '查看全部' })).toHaveAttribute('href', '/signals');
  });

  it('keeps the hard-error state retryable', async () => {
    vi.mocked(useUnreadNotifications).mockReturnValue(notificationState({ hasError: true }));
    renderBell();

    fireEvent.click(screen.getByRole('button', { name: '通知' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('暂时无法加载通知');
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('shows partial degradation and does not mark recovered items during the same open session', async () => {
    vi.mocked(useUnreadNotifications).mockReturnValue(notificationState({
      hasPartialError: true,
      signalsFailed: true,
    }));
    const { rerender } = renderBell();

    fireEvent.click(screen.getByRole('button', { name: '通知' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('部分通知暂时无法加载');
    expect(markAllSeen).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(refresh).toHaveBeenCalledTimes(1);

    vi.mocked(useUnreadNotifications).mockReturnValue(notificationState({
      signalItems: [{
        id: 7,
        stockCode: 'AAPL',
        action: 'buy',
        status: 'active',
        createdAt: '2026-07-23T10:00:00Z',
      } as UnreadNotificationsState['signalItems'][number]],
      unreadSignalCount: 1,
      unreadCount: 1,
    }));
    rerender(
      <MemoryRouter>
        <UiLanguageProvider initialLanguage="zh">
          <NotificationBell />
        </UiLanguageProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByRole('link', { name: /AAPL/ })).toBeInTheDocument();
    expect(markAllSeen).toHaveBeenCalledTimes(1);
  });

  it('marks server-ahead items seen when an open Bell finishes loading', async () => {
    vi.mocked(useUnreadNotifications)
      .mockReturnValueOnce(notificationState({ isLoading: true }))
      .mockReturnValue(notificationState({
        signalItems: [{
          id: 7,
          stockCode: 'AAPL',
          market: 'us',
          sourceType: 'analysis',
          triggerSource: 'analysis',
          action: 'buy',
          planQuality: 'complete',
          status: 'active',
          createdAt: '2026-07-23T10:00:00Z',
        }],
        unreadSignalCount: 1,
        unreadCount: 1,
      }));
    renderBell();

    fireEvent.click(screen.getByRole('button', { name: '通知' }));

    await waitFor(() => expect(markAllSeen).toHaveBeenCalledTimes(1));
  });

  it('caps the visual badge without changing the accessible unread count', async () => {
    vi.mocked(useUnreadNotifications).mockReturnValue(notificationState({ unreadCount: 125 }));
    renderBell();

    expect(screen.getByTestId('notification-unread-badge')).toHaveTextContent('99+');
    expect(screen.getByRole('button', { name: '通知，125 条未读' })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});
