// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { WatchlistGroupsPanel } from '../WatchlistGroupsPanel';
import type { WatchlistGroup } from '../../../types/watchlist';

const groups: WatchlistGroup[] = [
  {
    id: 'default',
    name: '__default__',
    nameKey: 'watchlist.defaultGroupName',
    sortOrder: 0,
    isDefault: true,
    createdAt: '2026-08-09T00:00:00+00:00',
    updatedAt: '2026-08-09T00:00:00+00:00',
    members: [
      { stockCode: '600519', sortOrder: 0, attrs: { schemaVersion: 1 } },
      { stockCode: 'AAPL', sortOrder: 1, attrs: { schemaVersion: 1 } },
    ],
  },
  {
    id: 'growth',
    name: 'Growth',
    nameKey: null,
    sortOrder: 1,
    isDefault: false,
    createdAt: '2026-08-09T00:00:00+00:00',
    updatedAt: '2026-08-09T00:00:00+00:00',
    members: [],
  },
];

function renderPanel(overrides: Partial<React.ComponentProps<typeof WatchlistGroupsPanel>> = {}) {
  const props: React.ComponentProps<typeof WatchlistGroupsPanel> = {
    groups,
    watchlistRows: [
      { code: '600519', analyzedToday: false },
      { code: 'AAPL', analyzedToday: true },
    ],
    onCreateGroup: vi.fn(async () => true),
    onDeleteGroup: vi.fn(async () => true),
    onReorderGroups: vi.fn(async () => true),
    onReorderMembers: vi.fn(async () => true),
    onMoveMember: vi.fn(async () => true),
    onRemoveFromWatchlist: vi.fn(async () => true),
    ...overrides,
  };
  render(<WatchlistGroupsPanel {...props} />);
  return props;
}

describe('WatchlistGroupsPanel', () => {
  it('uses a non-drag member row and an explicit desktop drag/keyboard handle', () => {
    const onReorderMembers = vi.fn(async () => true);
    renderPanel({ onReorderMembers });

    expect(screen.getByTestId('watchlist-member-default-600519')).not.toHaveAttribute('draggable');
    const handle = screen.getByRole('button', { name: '排序 600519；按上下方向键移动' });
    expect(handle).toHaveAttribute('draggable', 'true');
    fireEvent.keyDown(handle, { key: 'ArrowDown' });
    expect(onReorderMembers).toHaveBeenCalledWith('default', ['AAPL', '600519']);
  });

  it('supports mobile non-drag ordering and Move-to actions', async () => {
    const onReorderGroups = vi.fn(async () => true);
    const onMoveMember = vi.fn(async () => true);
    renderPanel({ onReorderGroups, onMoveMember });

    fireEvent.click(screen.getByRole('button', { name: '下移分组 默认分组' }));
    expect(onReorderGroups).toHaveBeenCalledWith(['growth', 'default']);
    fireEvent.click(screen.getByRole('button', { name: '600519 的分组操作' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Growth' }));
    expect(onMoveMember).toHaveBeenCalledWith({
      stockCode: '600519',
      sourceGroupId: 'default',
      targetGroupId: 'growth',
    });
    await waitFor(() => expect(screen.getByTestId('watchlist-groups-announcement')).toHaveTextContent(
      '已将 600519 移动到 Growth',
    ));
  });

  it('closes the member menu on Escape and restores trigger focus', () => {
    renderPanel();
    const trigger = screen.getByRole('button', { name: '600519 的分组操作' });
    fireEvent.click(trigger);
    expect(screen.getByRole('menu')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('creates a group from the form', async () => {
    const onCreateGroup = vi.fn(async () => true);
    renderPanel({ onCreateGroup });
    fireEvent.change(screen.getByRole('textbox', { name: '新分组名称' }), {
      target: { value: 'Value' },
    });
    fireEvent.click(screen.getByRole('button', { name: '创建分组' }));
    expect(onCreateGroup).toHaveBeenCalledWith('Value');
    await waitFor(() => expect(screen.getByRole('textbox', { name: '新分组名称' })).toHaveValue(''));
  });

  it('retains the create draft and suppresses success announcements when mutations fail', async () => {
    const onCreateGroup = vi.fn(async () => false);
    const onReorderGroups = vi.fn(async () => false);
    const onReorderMembers = vi.fn(async () => false);
    const onMoveMember = vi.fn(async () => false);
    renderPanel({ onCreateGroup, onReorderGroups, onReorderMembers, onMoveMember });

    const draft = screen.getByRole('textbox', { name: '新分组名称' });
    fireEvent.change(draft, { target: { value: 'Keep me' } });
    fireEvent.click(screen.getByRole('button', { name: '创建分组' }));
    await waitFor(() => expect(onCreateGroup).toHaveBeenCalledWith('Keep me'));
    expect(draft).toHaveValue('Keep me');

    fireEvent.click(screen.getByRole('button', { name: '下移分组 默认分组' }));
    await waitFor(() => expect(onReorderGroups).toHaveBeenCalled());
    fireEvent.keyDown(screen.getByRole('button', { name: '排序 600519；按上下方向键移动' }), {
      key: 'ArrowDown',
    });
    await waitFor(() => expect(onReorderMembers).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: '600519 的分组操作' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Growth' }));
    await waitFor(() => expect(onMoveMember).toHaveBeenCalled());

    expect(screen.getByTestId('watchlist-groups-announcement')).toBeEmptyDOMElement();
  });
});
