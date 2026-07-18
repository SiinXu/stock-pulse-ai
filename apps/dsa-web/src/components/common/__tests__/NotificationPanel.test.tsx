import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { NotificationPanel } from '../NotificationPanel';

describe('NotificationPanel', () => {
  it('renders the Figma-sized empty notification state', () => {
    render(<NotificationPanel title="Notifications" emptyText="No notifications" filterLabel="All" />);

    expect(screen.getByRole('heading', { name: 'Notifications' }).closest('section')).toHaveClass('w-67', 'min-h-57', 'rounded-xl');
    expect(screen.getByText('No notifications')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument();
  });
});
