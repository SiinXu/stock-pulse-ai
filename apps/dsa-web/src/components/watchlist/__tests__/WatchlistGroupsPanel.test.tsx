// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WatchlistGroupsPanel } from '../WatchlistGroupsPanel';
import type { WatchlistGroup } from '../../../types/watchlist';

const groups: WatchlistGroup[] = [
  {
    id: 'default',
    name: 'Default',
    sortOrder: 0,
    isDefault: true,
    createdAt: '2026-08-09T00:00:00',
    updatedAt: '2026-08-09T00:00:00',
    members: [
      { stockCode: '600519', sortOrder: 0, attrs: {} },
      { stockCode: 'AAPL', sortOrder: 1, attrs: {} },
    ],
  },
  {
    id: 'growth',
    name: 'Growth',
    sortOrder: 1,
    isDefault: false,
    createdAt: '2026-08-09T00:00:00',
    updatedAt: '2026-08-09T00:00:00',
    members: [],
  },
];

describe('WatchlistGroupsPanel', () => {
  it('renders groups and supports non-drag Move-to menu path', async () => {
    const onMoveMember = vi.fn(async () => undefined);
    render(
      <WatchlistGroupsPanel
        groups={groups}
        watchlistRows={[
          { code: '600519', analyzedToday: false },
          { code: 'AAPL', analyzedToday: true },
        ]}
        onCreateGroup={vi.fn()}
        onDeleteGroup={vi.fn()}
        onReorderGroups={vi.fn()}
        onReorderMembers={vi.fn()}
        onMoveMember={onMoveMember}
        onRemoveFromWatchlist={vi.fn(async () => true)}
      />,
    );

    expect(screen.getByTestId('watchlist-groups-panel')).toBeInTheDocument();
    expect(screen.getByTestId('watchlist-group-default')).toBeInTheDocument();
    expect(screen.getByText('Growth')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '600519 的分组操作' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Growth' }));

    expect(onMoveMember).toHaveBeenCalledWith({
      stockCode: '600519',
      sourceGroupId: 'default',
      targetGroupId: 'growth',
    });
  });

  it('creates a group from the form', async () => {
    const onCreateGroup = vi.fn(async () => undefined);
    render(
      <WatchlistGroupsPanel
        groups={groups}
        watchlistRows={[]}
        onCreateGroup={onCreateGroup}
        onDeleteGroup={vi.fn()}
        onReorderGroups={vi.fn()}
        onReorderMembers={vi.fn()}
        onMoveMember={vi.fn()}
        onRemoveFromWatchlist={vi.fn(async () => true)}
      />,
    );

    fireEvent.change(screen.getByRole('textbox', { name: '新分组名称' }), {
      target: { value: 'Value' },
    });
    fireEvent.click(screen.getByRole('button', { name: '创建分组' }));
    expect(onCreateGroup).toHaveBeenCalledWith('Value');
  });
});
