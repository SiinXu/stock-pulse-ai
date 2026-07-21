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

  it('keeps the provider directory inline and mounts fields only in the shared dialog', () => {
    renderPanel([
      buildItem('TUSHARE_TOKEN', ''),
      buildItem('TAVILY_API_KEYS', 'key-1'),
    ]);

    const trigger = screen.getByRole('button', { name: /Tushare/ });
    expect(screen.getByRole('heading', { name: '行情源' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '搜索源' })).toBeInTheDocument();
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
});
