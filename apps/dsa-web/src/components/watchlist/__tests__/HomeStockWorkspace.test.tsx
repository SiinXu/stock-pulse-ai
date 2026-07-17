import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HomeStockWorkspace } from '../HomeStockWorkspace';
import type { HomeWorkspaceTab } from '../HomeStockWorkspace';

const buildProps = (activeTab: HomeWorkspaceTab, onTabChange = vi.fn()) => ({
  activeTab,
  onTabChange,
  watchlistRows: [],
  watchlistLoading: false,
  watchlistActioning: false,
  watchlistMessage: null,
  onAddToWatchlist: vi.fn(async () => undefined),
  onRemoveFromWatchlist: vi.fn(async () => undefined),
  onRefreshWatchlist: vi.fn(async () => undefined),
  onAnalyzeWatchlist: vi.fn(async () => undefined),
  isBatchAnalyzing: false,
  batchStatus: null,
  todayItems: [],
  isLoadingTodayItems: false,
  todayLoadError: false,
  watchlistAnalyzedTodayCount: 0,
  historyItems: [],
  isLoadingHistory: false,
  onHistoryItemClick: vi.fn(),
});

describe('HomeStockWorkspace', () => {
  it('keeps add and remove icon actions at least 44px square', () => {
    render(
      <HomeStockWorkspace
        activeTab="watchlist"
        onTabChange={vi.fn()}
        watchlistRows={[{ code: '600519', analyzedToday: false }]}
        watchlistLoading={false}
        watchlistActioning={false}
        watchlistMessage={null}
        onAddToWatchlist={vi.fn(async () => undefined)}
        onRemoveFromWatchlist={vi.fn(async () => undefined)}
        onRefreshWatchlist={vi.fn(async () => undefined)}
        onAnalyzeWatchlist={vi.fn(async () => undefined)}
        isBatchAnalyzing={false}
        batchStatus={null}
        todayItems={[]}
        isLoadingTodayItems={false}
        todayLoadError={false}
        watchlistAnalyzedTodayCount={0}
        historyItems={[]}
        isLoadingHistory={false}
        onHistoryItemClick={vi.fn()}
      />,
    );

    expect(screen.getByRole('tablist', { name: '工作台视图切换' })).toHaveClass('h-11');
    expect(screen.getByRole('searchbox', { name: '搜索' })).toHaveClass('h-11');
    expect(screen.getByRole('textbox', { name: '添加代码，如 600519' })).toHaveClass('h-11');
    expect(screen.getByRole('button', { name: '添加自选股' })).toHaveClass('h-11', 'w-11');
    expect(screen.getByRole('button', { name: '从自选股移除 600519' })).toHaveClass('h-11', 'w-11');
  });

  it('keeps the busy add action spinner-only inside its fixed icon target', () => {
    render(
      <HomeStockWorkspace
        activeTab="watchlist"
        onTabChange={vi.fn()}
        watchlistRows={[]}
        watchlistLoading={false}
        watchlistActioning
        watchlistMessage={null}
        onAddToWatchlist={vi.fn(async () => undefined)}
        onRemoveFromWatchlist={vi.fn(async () => undefined)}
        onRefreshWatchlist={vi.fn(async () => undefined)}
        onAnalyzeWatchlist={vi.fn(async () => undefined)}
        isBatchAnalyzing={false}
        batchStatus={null}
        todayItems={[]}
        isLoadingTodayItems={false}
        todayLoadError={false}
        watchlistAnalyzedTodayCount={0}
        historyItems={[]}
        isLoadingHistory={false}
        onHistoryItemClick={vi.fn()}
      />,
    );

    const addButton = screen.getByRole('button', { name: '添加自选股' });
    expect(addButton).toHaveClass('h-11', 'w-11');
    expect(addButton).toHaveAttribute('aria-busy', 'true');
    expect(addButton.textContent).toBe('');
    expect(addButton.querySelector('svg.animate-spin')).toBeInTheDocument();
  });

  it.each<HomeWorkspaceTab>(['history', 'watchlist', 'today'])(
    'keeps the tablist outside the switching panel on the %s tab',
    (activeTab) => {
      render(<HomeStockWorkspace {...buildProps(activeTab)} />);

      const tablist = screen.getByRole('tablist', { name: '工作台视图切换' });
      const tabs = screen.getAllByRole('tab');
      expect(tabs).toHaveLength(3);

      const selected = screen.getByRole('tab', { selected: true });
      const panel = screen.getByRole('tabpanel');
      expect(panel).toHaveAttribute('aria-labelledby', selected.id);
      expect(tabs.every((tab) => tab.getAttribute('aria-controls') === panel.id)).toBe(true);

      // The unified shell: filter toolbar and panel are siblings, so controls
      // keep the same position/size no matter which tab renders.
      expect(tablist.parentElement?.parentElement).toBe(panel.parentElement);
      expect(panel.contains(tablist)).toBe(false);
    },
  );

  it('moves selection with arrow keys and keeps a roving tabindex', () => {
    const onTabChange = vi.fn();
    render(<HomeStockWorkspace {...buildProps('history', onTabChange)} />);

    const [historyTab, watchlistTab, todayTab] = screen.getAllByRole('tab');
    expect(historyTab).toHaveAttribute('tabindex', '0');
    expect(watchlistTab).toHaveAttribute('tabindex', '-1');
    expect(todayTab).toHaveAttribute('tabindex', '-1');

    fireEvent.keyDown(historyTab, { key: 'ArrowRight' });
    expect(onTabChange).toHaveBeenCalledWith('watchlist');

    fireEvent.keyDown(historyTab, { key: 'End' });
    expect(onTabChange).toHaveBeenCalledWith('today');

    fireEvent.keyDown(historyTab, { key: 'ArrowLeft' });
    expect(onTabChange).toHaveBeenCalledWith('today');
  });
});
