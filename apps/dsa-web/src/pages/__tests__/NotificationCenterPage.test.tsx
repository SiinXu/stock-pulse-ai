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
            id: 'analysis_complete:1',
            kind: 'analysis_complete',
            title: 'Analysis complete: 600519',
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
        retentionDays: 90,
        maxItems: 500,
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: 'analysis_complete:1',
            kind: 'analysis_complete',
            title: 'Analysis complete: 600519',
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
        retentionDays: 90,
        maxItems: 500,
      });
    markReadMock.mockResolvedValue({ markedCount: 1, unreadTotal: 0 });

    renderPage();
    expect(await screen.findByText('Analysis complete: 600519')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Mark read' }));
    await waitFor(() => {
      expect(markReadMock).toHaveBeenCalledWith(['analysis_complete:1']);
    });
  });
});
