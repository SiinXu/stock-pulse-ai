// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
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

function renderPage() {
  return render(
    <UiLanguageProvider initialLanguage="en">
      <MemoryRouter>
        <NotificationCenterPage />
      </MemoryRouter>
    </UiLanguageProvider>,
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
      'Some notification sources are temporarily unavailable',
    );
    expect(screen.getByTestId('notification-center-empty')).toBeInTheDocument();
  });
});
