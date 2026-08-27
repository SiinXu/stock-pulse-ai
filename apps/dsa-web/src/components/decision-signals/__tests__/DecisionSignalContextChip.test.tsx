// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { DecisionSignalItem } from '../../../types/decisionSignals';
import { DecisionSignalContextChip } from '../DecisionSignalContextChip';

const item: DecisionSignalItem = {
  id: 7,
  stockCode: '600519',
  stockName: '贵州茅台',
  market: 'cn',
  sourceType: 'analysis',
  sourceReportId: 3001,
  triggerSource: 'web',
  action: 'hold',
  planQuality: 'complete',
  status: 'active',
};

function renderChip(onOpen = vi.fn(), language: 'zh' | 'en' = 'zh') {
  window.localStorage.setItem('dsa.uiLanguage', language);
  render(
    <UiLanguageProvider>
      <DecisionSignalContextChip
        selected={{ source: 'list', item }}
        onOpen={onOpen}
      />
    </UiLanguageProvider>,
  );
  return onOpen;
}

describe('DecisionSignalContextChip', () => {
  it('shows symbol, labeled source, and status in Simplified Chinese and reopens details on click', () => {
    const onOpen = renderChip();
    const chip = screen.getByTestId('decision-signal-context-chip');
    expect(chip).toHaveAttribute('data-selected-signal-id', '7');
    expect(chip).toHaveAccessibleName('600519 贵州茅台, 来源 分析报告, 状态 有效');
    fireEvent.click(screen.getByRole('button', { name: '查看详情 600519 贵州茅台' }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('shows symbol, labeled source, and status in English with locale-neutral separators', () => {
    const onOpen = renderChip(vi.fn(), 'en');
    const chip = screen.getByTestId('decision-signal-context-chip');
    expect(chip).toHaveAttribute('data-selected-signal-id', '7');
    expect(chip).toHaveAccessibleName('600519 贵州茅台, Source Analysis report, Status Active');
    fireEvent.click(screen.getByRole('button', { name: 'View details 600519 贵州茅台' }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('renders nothing when no signal is selected', () => {
    window.localStorage.setItem('dsa.uiLanguage', 'zh');
    render(
      <UiLanguageProvider>
        <DecisionSignalContextChip selected={null} onOpen={vi.fn()} />
      </UiLanguageProvider>,
    );
    expect(screen.queryByTestId('decision-signal-context-chip')).not.toBeInTheDocument();
  });
});
