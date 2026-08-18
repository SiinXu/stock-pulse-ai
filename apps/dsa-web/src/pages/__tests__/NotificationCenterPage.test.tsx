// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  RouteFocusRegistrationContext,
  type RouteFocusTarget,
} from '../../contexts/routeFocusContext';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import { chooseOption, createDeferred } from '../../test-utils';
import type { NotificationInboxItem, NotificationInboxPage } from '../../types/notificationInbox';
import NotificationCenterPage from '../NotificationCenterPage';

const listMock = vi.fn();
const markReadMock = vi.fn();
const markAllReadMock = vi.fn();

vi.mock('../../api/notificationInbox', () => ({
  notificationInboxApi: {
    list: (...args: unknown[]) => listMock(...args),
    markRead: (...args: unknown[]) => markReadMock(...args),
    markAllRead: (...args: unknown[]) => markAllReadMock(...args),
    unreadCount: vi.fn(),
  },
}));

const routeFocusRegister = vi.fn((target: RouteFocusTarget) => {
  void target;
  return () => {};
});

function emptyPage(overrides: Partial<NotificationInboxPage> = {}): NotificationInboxPage {
  return {
    items: [],
    page: 1,
    pageSize: 50,
    total: 0,
    unreadTotal: 0,
    hasMore: false,
    sourceStatuses: [],
    retentionDays: 90,
    maxItems: 500,
    ...overrides,
  };
}

function inboxItem(overrides: Partial<NotificationInboxItem> = {}): NotificationInboxItem {
  return {
    id: 'v1:analysis_complete:1:1786233600000000',
    kind: 'analysis_complete',
    titleKey: 'analysisCompleteTitle',
    titleParams: { label: '600519' },
    summary: 'hold',
    severity: 'info',
    createdAt: '2026-08-09T00:00:00Z',
    isRead: false,
    href: '/research/analysis?segment=history&recordId=1',
    sourceId: '1',
    ...overrides,
  };
}

function renderPage() {
  return render(
    <RouteFocusRegistrationContext.Provider value={{ register: routeFocusRegister }}>
        <UiLanguageProvider initialLanguage="en">
      <MemoryRouter>
        <NotificationCenterPage />
      </MemoryRouter>
    </UiLanguageProvider>
      </RouteFocusRegistrationContext.Provider>,
  );
}


describe('NotificationCenterPage', () => {
  beforeEach(() => {
    listMock.mockReset();
    markReadMock.mockReset();
    markAllReadMock.mockReset();
  });

  it('renders empty state when inbox has no items', async () => {
    listMock.mockResolvedValue({
      items: [],
      page: 1,
      pageSize: 50,
      total: 0,
      unreadTotal: 0,
      hasMore: false,
      sourceStatuses: [],
      retentionDays: 90,
      maxItems: 500,
    });
    renderPage();
    expect(await screen.findByTestId('notification-center-empty')).toBeInTheDocument();
    expect(screen.getByText('No notifications yet')).toBeInTheDocument();
  });

  it('lists items and marks one as read', async () => {
    listMock
      .mockResolvedValueOnce({
        items: [
          {
            id: 'v1:analysis_complete:1:1786233600000000',
            kind: 'analysis_complete',
            titleKey: 'analysisCompleteTitle',
            titleParams: { label: '600519' },
            summary: 'hold',
            severity: 'info',
            createdAt: '2026-08-09T00:00:00Z',
            isRead: false,
            href: '/research/analysis?segment=history&recordId=1',
            sourceId: '1',
          },
        ],
        page: 1,
        pageSize: 50,
        total: 1,
        unreadTotal: 1,
        hasMore: false,
        sourceStatuses: [],
        retentionDays: 90,
        maxItems: 500,
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: 'v1:analysis_complete:1:1786233600000000',
            kind: 'analysis_complete',
            titleKey: 'analysisCompleteTitle',
            titleParams: { label: '600519' },
            summary: 'hold',
            severity: 'info',
            createdAt: '2026-08-09T00:00:00Z',
            isRead: true,
            href: '/research/analysis?segment=history&recordId=1',
            sourceId: '1',
          },
        ],
        page: 1,
        pageSize: 50,
        total: 1,
        unreadTotal: 0,
        hasMore: false,
        sourceStatuses: [],
        retentionDays: 90,
        maxItems: 500,
      });
    markReadMock.mockResolvedValue({ markedCount: 1, unreadTotal: 0 });

    renderPage();
    expect(await screen.findByText('Analysis complete: 600519')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Mark read' }));
    await waitFor(() => {
      expect(markReadMock).toHaveBeenCalledWith([
        'v1:analysis_complete:1:1786233600000000',
      ]);
    });
  });

  it('uses the cursor to append reachable overflow items', async () => {
    listMock
      .mockResolvedValueOnce({
        items: [{
          id: 'v1:analysis_complete:1:1786233600000000',
          kind: 'analysis_complete',
          titleKey: 'analysisCompleteTitle',
          titleParams: { label: 'AAPL' },
          summary: 'Hold',
          severity: 'info',
          createdAt: '2026-08-10T00:00:00Z',
          isRead: false,
          href: '/research/analysis?segment=history&recordId=1',
          sourceId: '1',
        }],
        page: 1,
        pageSize: 50,
        total: 2,
        unreadTotal: 2,
        nextCursor: 'cursor-1',
        hasMore: true,
        sourceStatuses: [],
        retentionDays: 90,
        maxItems: 500,
      })
      .mockResolvedValueOnce({
        items: [{
          id: 'v1:alert_triggered:2:1786233500000000',
          kind: 'alert_triggered',
          titleKey: 'alertTriggeredTitle',
          titleParams: { target: 'MSFT' },
          summary: 'Threshold crossed',
          severity: 'warning',
          createdAt: '2026-08-09T23:58:20Z',
          isRead: false,
          href: '/signals?tab=history&trigger=2',
          sourceId: '2',
        }],
        page: 1,
        pageSize: 50,
        total: 2,
        unreadTotal: 2,
        hasMore: false,
        sourceStatuses: [],
        retentionDays: 90,
        maxItems: 500,
      });

    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Load more' }));

    expect(await screen.findByText('Alert triggered: MSFT')).toBeInTheDocument();
    expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: 'cursor-1' }));
    expect(screen.getByText('Analysis complete: AAPL')).toBeInTheDocument();
  });

  it('keeps partial-source provenance visible with available rows', async () => {
    listMock.mockResolvedValue({
      items: [],
      page: 1,
      pageSize: 50,
      total: 0,
      unreadTotal: 0,
      hasMore: false,
      sourceStatuses: [{
        source: 'alerts',
        available: false,
        itemCount: 0,
        errorCode: 'alerts_unavailable',
      }],
      retentionDays: 90,
      maxItems: 500,
    });

    renderPage();

    expect(await screen.findByTestId('notification-center-partial-source')).toHaveTextContent(
      'Some notifications are temporarily unavailable.',
    );
    expect(screen.getByTestId('notification-center-empty')).toBeInTheDocument();
  });

  it('shows a retryable error without the empty state when the inbox load fails', async () => {
    listMock.mockRejectedValue(new Error('inbox unavailable'));
    renderPage();

    expect(await screen.findByRole('alert', { name: 'Unable to load the notification center' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.queryByTestId('notification-center-empty')).not.toBeInTheDocument();
    expect(screen.queryByText('No notifications yet')).not.toBeInTheDocument();
  });

  it('retries the inbox request and clears the error after a successful reload', async () => {
    listMock
      .mockRejectedValueOnce(new Error('inbox unavailable'))
      .mockResolvedValueOnce(emptyPage());
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Retry' }));

    expect(await screen.findByTestId('notification-center-empty')).toBeInTheDocument();
    expect(screen.queryByRole('alert', { name: 'Unable to load the notification center' })).not.toBeInTheDocument();
    expect(listMock).toHaveBeenCalledTimes(2);
  });

  it('keeps the latest kind filter response when requests resolve out of order', async () => {
    const allRequest = createDeferred<NotificationInboxPage>();
    const alertRequest = createDeferred<NotificationInboxPage>();
    listMock
      .mockReturnValueOnce(allRequest.promise)
      .mockReturnValueOnce(alertRequest.promise);

    renderPage();
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));

    chooseOption(screen.getByRole('combobox', { name: 'All types' }), 'alert_triggered');
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2));
    expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'alert_triggered' }));

    alertRequest.resolve(emptyPage({
      items: [inboxItem({
        id: 'v1:alert_triggered:2:1786233500000000',
        kind: 'alert_triggered',
        titleKey: 'alertTriggeredTitle',
        titleParams: { target: 'MSFT' },
        summary: 'Threshold crossed',
        severity: 'warning',
        createdAt: '2026-08-09T23:58:20Z',
        href: '/signals?tab=history&trigger=2',
        sourceId: '2',
      })],
      total: 1,
      unreadTotal: 1,
    }));
    expect(await screen.findByText('Alert triggered: MSFT')).toBeInTheDocument();

    allRequest.resolve(emptyPage({
      items: [inboxItem({
        id: 'v1:analysis_complete:1:1786233600000000',
        titleParams: { label: 'STALE' },
        summary: 'stale all-types row',
      })],
      total: 1,
      unreadTotal: 1,
    }));

    await waitFor(() => {
      expect(screen.queryByText('Analysis complete: STALE')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Alert triggered: MSFT')).toBeInTheDocument();
  });
});
