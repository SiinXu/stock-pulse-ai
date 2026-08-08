// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { StockBarItem } from '../../../types/analysis';
import { StockBar } from '../StockBar';

const item: StockBarItem = {
  id: 1,
  stockCode: '600519',
  stockName: '贵州茅台',
  sentimentScore: 62,
  operationAdvice: '观望',
  analysisCount: 1,
  lastAnalysisTime: '2026-07-15T08:00:00Z',
};

describe('StockBar', () => {
  it('uses 44px labels for batch and row selection checkboxes', () => {
    render(
      <StockBar
        items={[item]}
        isLoading={false}
        onItemClick={vi.fn()}
        onDeleteStock={vi.fn(async () => undefined)}
      />,
    );

    expect(screen.getByRole('checkbox', { name: '全选当前个股' }).closest('label')).toHaveClass('min-h-11');
    expect(screen.getByRole('checkbox', { name: '选择 贵州茅台 历史记录' }).closest('label')).toHaveClass('h-11', 'w-11');
    expect(screen.getByRole('button', { name: '删除' })).toHaveAttribute('data-control', 'icon-button');
  });

  it('exposes a min-h-0 height chain for the stock-bar scroll viewport', () => {
    const { container } = render(
      <StockBar
        items={[item]}
        isLoading={false}
        onItemClick={vi.fn()}
        className="min-h-0 flex-1 overflow-hidden"
      />,
    );

    const root = container.firstElementChild;
    expect(root).toHaveClass('min-h-0');
    const viewport = screen.getByTestId('home-stock-bar-scroll');
    expect(viewport).toHaveClass('min-h-0', 'overflow-y-auto');
    expect(viewport.parentElement).toHaveClass('min-h-0', 'flex-1');
  });
});
