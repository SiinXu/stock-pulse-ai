// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SystemConfigItem } from '../../../types/systemConfig';
import { DataProvidersPanel } from '../DataProvidersPanel';

// SettingsField pulls settingsHelp, whose en inventory is currently stale on main
// for newly added data_source keys (RSS_NEWS_*). Mock the field shell so this
// hub suite stays focused on card/filter/dialog contracts without that debt.
vi.mock('../SettingsField', () => ({
  SettingsField: ({ item }: { item: { key: string } }) => (
    <div id={`setting-${item.key}`} data-testid={`setting-${item.key}`} />
  ),
}));

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
  it('groups provider cards by hub role with capability and status chips', () => {
    renderPanel(
      [
        buildItem('TUSHARE_TOKEN', ''),
        buildItem('TICKFLOW_API_KEY', 'tf-key'),
        buildItem('TICKFLOW_PRIORITY', 'high'),
        buildItem('TAVILY_API_KEYS', ''),
      ],
    );

    expect(screen.getByRole('heading', { name: '默认路径' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '增强器' })).toBeInTheDocument();

    // Keyless baselines always appear with honest unknown as-of.
    expect(screen.getByText('AkShare')).toBeInTheDocument();
    expect(screen.getByText('yfinance')).toBeInTheDocument();
    expect(document.getElementById('data-provider-akshare')).toHaveAttribute(
      'data-provider-role',
      'baseline',
    );

    const tushareCard = screen.getByRole('button', { name: /Tushare/ });
    expect(within(tushareCard).getByText('未配置')).toBeInTheDocument();
    expect(within(tushareCard).getByText('基本面')).toBeInTheDocument();
    expect(within(tushareCard).getByText('增强器')).toBeInTheDocument();
    expect(tushareCard).toHaveAttribute('id', 'data-provider-tushare');

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
    expect(within(alphasiftCard).getByText('高级')).toBeInTheDocument();
  });

  it('filters cards by search query and role chips', () => {
    renderPanel([
      buildItem('TUSHARE_TOKEN', 'tok'),
      buildItem('TAVILY_API_KEYS', 'key-1'),
      buildItem('PYTDX_HOST', '127.0.0.1'),
    ]);

    const filters = screen.getByRole('group', { name: '数据源筛选' });
    fireEvent.click(within(filters).getByRole('button', { name: '增强器' }));
    expect(screen.getByRole('button', { name: /Tushare/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Tavily/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Pytdx/ })).not.toBeInTheDocument();
    expect(screen.queryByText('AkShare')).not.toBeInTheDocument();

    fireEvent.click(within(filters).getByRole('button', { name: '全部角色' }));
    const search = screen.getByRole('searchbox', { name: '按名称、类型或状态筛选数据源' });
    fireEvent.change(search, { target: { value: 'tushare' } });
    expect(screen.getByRole('button', { name: /Tushare/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Tavily/ })).not.toBeInTheDocument();
  });

  it('keeps the provider directory inline and mounts fields only in the shared dialog', () => {
    renderPanel([
      buildItem('TUSHARE_TOKEN', ''),
      buildItem('TAVILY_API_KEYS', 'key-1'),
    ]);

    const trigger = screen.getByRole('button', { name: /Tushare/ });
    expect(screen.getByRole('heading', { name: '增强器' })).toBeInTheDocument();
    expect(within(trigger).getByText('未配置')).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /Tavily/ })).getByText('已配置')).toBeInTheDocument();
    expect(document.querySelector('#setting-TUSHARE_TOKEN')).toBeNull();

    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole('dialog', { name: 'Tushare' });
    expect(dialog).toHaveAttribute('data-overlay-dialog', 'true');
    // SettingsField renders localized titles; assert on stable control ids.
    const providerField = dialog.querySelector('#setting-TUSHARE_TOKEN');
    expect(providerField).not.toBeNull();
    expect(providerField?.closest('[role="dialog"]')).toBe(dialog);
    expect(dialog.querySelector('#setting-TAVILY_API_KEYS')).toBeNull();

    fireEvent.keyDown(dialog, { key: 'Escape' });

    expect(screen.queryByRole('dialog', { name: 'Tushare' })).not.toBeInTheDocument();
    expect(document.querySelector('#setting-TUSHARE_TOKEN')).toBeNull();
    expect(trigger).toHaveFocus();
    expect(within(trigger).getByText('未配置')).toBeInTheDocument();
  });

  it('exposes stable hub anchors for deep links', () => {
    renderPanel([buildItem('TUSHARE_TOKEN', '')]);
    expect(document.getElementById('data-sources-providers')).toBeInTheDocument();
    expect(document.getElementById('data-provider-tushare')).toBeInTheDocument();
    expect(document.getElementById('data-sources-role-baseline')).toBeInTheDocument();
  });
});
