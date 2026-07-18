// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SystemConfigItem } from '../../../types/systemConfig';
import { DataProvidersPanel } from '../DataProvidersPanel';

function buildItem(key: string, value: string): SystemConfigItem {
  return {
    key,
    value,
    rawValueExists: value !== '',
    isMasked: false,
    schema: {
      key,
      category: 'data_source',
      dataType: 'string',
      uiControl: 'text',
      isSensitive: false,
      isRequired: false,
      isEditable: true,
      options: [],
      validation: {},
      displayOrder: 1,
    },
  };
}

// No UiLanguageProvider wrapper: useUiLanguage falls back to the zh context,
// keeping assertions deterministic regardless of the jsdom navigator locale.
function renderPanel(items: SystemConfigItem[], configuredOverrides?: Record<string, boolean>) {
  render(
    <DataProvidersPanel
      items={items}
      disabled={false}
      onChange={vi.fn()}
      issueByKey={{}}
      configuredOverrides={configuredOverrides}
    />,
  );
}

describe('DataProvidersPanel', () => {
  it('groups provider cards into quote and search sections with configured badges', () => {
    renderPanel(
      [
        buildItem('TUSHARE_TOKEN', ''),
        buildItem('TICKFLOW_API_KEY', 'tf-key'),
        buildItem('TICKFLOW_PRIORITY', 'high'),
        buildItem('TAVILY_API_KEYS', ''),
      ],
    );

    expect(screen.getByRole('heading', { name: '行情源' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '搜索源' })).toBeInTheDocument();

    const tushareCard = screen.getByRole('button', { name: /Tushare/ });
    expect(within(tushareCard).getByText('未配置')).toBeInTheDocument();

    const tickflowCard = screen.getByRole('button', { name: /TickFlow/ });
    expect(within(tickflowCard).getByText('已配置')).toBeInTheDocument();

    // Providers without any matching items are not rendered.
    expect(screen.queryByRole('button', { name: /Pytdx/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Brave/ })).not.toBeInTheDocument();
  });

  it('does not mark a provider configured from non-credential defaults', () => {
    renderPanel([
      buildItem('TICKFLOW_API_KEY', ''),
      buildItem('TICKFLOW_PRIORITY', 'high'),
      buildItem('TICKFLOW_KLINE_ADJUST', 'qfq'),
    ]);

    const tickflowCard = screen.getByRole('button', { name: /TickFlow/ });
    expect(within(tickflowCard).getByText('未配置')).toBeInTheDocument();
  });

  it('honors configured overrides for externally managed providers', () => {
    renderPanel([buildItem('ALPHASIFT_INSTALL_SPEC', '')], { alphasift: true });

    const alphasiftCard = screen.getByRole('button', { name: /AlphaSift/ });
    expect(within(alphasiftCard).getByText('已配置')).toBeInTheDocument();
  });

  it('opens a config dialog with only the provider fields', () => {
    renderPanel([
      buildItem('TUSHARE_TOKEN', ''),
      buildItem('TAVILY_API_KEYS', 'key-1'),
    ]);

    fireEvent.click(screen.getByRole('button', { name: /Tushare/ }));

    const dialog = screen.getByRole('dialog');
    // SettingsField renders localized titles; assert on stable control ids.
    expect(dialog.querySelector('#setting-TUSHARE_TOKEN')).not.toBeNull();
    expect(dialog.querySelector('#setting-TAVILY_API_KEYS')).toBeNull();
  });
});
