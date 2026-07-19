import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { NotificationPanel } from '../NotificationPanel';

describe('NotificationPanel', () => {
  it('renders the Figma-sized empty notification state', () => {
    render(<NotificationPanel title="Notifications" emptyText="No notifications" filterLabel="All" />);

    expect(screen.getByRole('heading', { name: 'Notifications' }).closest('section')).toHaveClass('w-67', 'min-h-57', 'rounded-xl');
    expect(screen.getByText('No notifications')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument();
  });

  it('renders loading, error, and retry states inside the same card', () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <UiLanguageProvider>
        <NotificationPanel title="Notifications" emptyText="No notifications" isLoading loadingText="Loading notifications" />
      </UiLanguageProvider>,
    );
    expect(screen.getByRole('status')).toHaveTextContent('Loading notifications');

    rerender(
      <UiLanguageProvider>
        <NotificationPanel
          title="Notifications"
          emptyText="No notifications"
          errorText="Could not load notifications"
          retryLabel="Retry"
          onRetry={onRetry}
        />
      </UiLanguageProvider>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load notifications');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('renders selectable notification rows and unread semantics', () => {
    const onSelect = vi.fn();
    render(
      <NotificationPanel
        title="Notifications"
        emptyText="No notifications"
        unreadLabel="Unread"
        items={[
          {
            id: 1,
            title: 'Analysis complete',
            description: 'AAPL report is ready',
            meta: 'Just now',
            unread: true,
            onSelect,
          },
        ]}
      />,
    );

    const row = screen.getByRole('button', { name: /Analysis completeUnread/ });
    expect(row).toHaveClass('min-h-11');
    fireEvent.click(row);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.getByText('AAPL report is ready')).toBeInTheDocument();
  });
});
