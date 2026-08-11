// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SystemConfigItem } from '../../../types/systemConfig';
import { DataProvidersPanel } from '../DataProvidersPanel';
import { isDataProviderKey } from '../dataProviders';

function buildItem(
  key: string,
  value: string,
  rawValueExists = value !== '',
): SystemConfigItem {
  return {
    key,
    value,
    rawValueExists,
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
  it('shows only market-provider configuration owners with truthful scope copy', () => {
    renderPanel(
      [
        buildItem('TUSHARE_TOKEN', ''),
        buildItem('TICKFLOW_API_KEY', 'tf-key'),
        buildItem('TAVILY_API_KEYS', 'search-key'),
        buildItem('FUTU_OPEND_HOST', '127.0.0.1', false),
      ],
    );

    expect(screen.getByText(/只显示已保存的行情提供方设置/)).toBeInTheDocument();

    const tushareCard = screen.getByRole('button', { name: /Tushare/ });
    expect(within(tushareCard).getByText('未配置')).toBeInTheDocument();

    const tickflowCard = screen.getByRole('button', { name: /TickFlow/ });
    expect(within(tickflowCard).getByText('已配置')).toBeInTheDocument();

    expect(screen.queryByRole('button', { name: /Tavily/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Futu/ })).not.toBeInTheDocument();
    expect(isDataProviderKey('TAVILY_API_KEYS')).toBe(false);
    expect(isDataProviderKey('FUTU_OPEND_HOST')).toBe(false);
  });

  it('does not treat inherited endpoint defaults as explicit configuration', () => {
    renderPanel([
      buildItem('PYTDX_HOST', '127.0.0.1', false),
      buildItem('PYTDX_PORT', '7709', false),
    ]);

    const pytdxCard = screen.getByRole('button', { name: /Pytdx/ });
    expect(within(pytdxCard).getByText('未配置')).toBeInTheDocument();
  });

  it('honors configured overrides for externally managed providers', () => {
    renderPanel([buildItem('ALPHASIFT_INSTALL_SPEC', '')], { alphasift: true });

    const alphasiftCard = screen.getByRole('button', { name: /AlphaSift/ });
    expect(within(alphasiftCard).getByText('已配置')).toBeInTheDocument();
  });

  it('filters by provider name and explicit configuration state', () => {
    renderPanel([
      buildItem('TUSHARE_TOKEN', ''),
      buildItem('TICKFLOW_API_KEY', 'tf-key'),
      buildItem('PYTDX_HOST', '127.0.0.1', false),
    ]);

    fireEvent.click(screen.getByRole('button', { name: '已配置' }));
    expect(screen.getByRole('button', { name: /TickFlow/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Tushare/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '全部配置' }));
    fireEvent.change(screen.getByRole('searchbox', { name: '按名称或配置状态筛选' }), {
      target: { value: 'pytdx' },
    });
    expect(screen.getByRole('button', { name: /Pytdx/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /TickFlow/ })).not.toBeInTheDocument();
  });

  it('mounts the real shared SettingsField only inside the modal and returns focus', () => {
    renderPanel([
      buildItem('TUSHARE_TOKEN', ''),
    ]);

    const trigger = screen.getByRole('button', { name: /Tushare/ });
    expect(within(trigger).getByText('未配置')).toBeInTheDocument();
    expect(document.querySelector('#setting-TUSHARE_TOKEN')).toBeNull();

    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole('dialog', { name: 'Tushare' });
    expect(dialog).toHaveAttribute('data-overlay-dialog', 'true');
    // SettingsField renders localized titles; assert on stable control ids.
    const providerField = dialog.querySelector('#setting-TUSHARE_TOKEN');
    expect(providerField).not.toBeNull();
    expect(providerField?.closest('[role="dialog"]')).toBe(dialog);

    fireEvent.keyDown(dialog, { key: 'Escape' });

    expect(screen.queryByRole('dialog', { name: 'Tushare' })).not.toBeInTheDocument();
    expect(document.querySelector('#setting-TUSHARE_TOKEN')).toBeNull();
    expect(trigger).toHaveFocus();
    expect(within(trigger).getByText('未配置')).toBeInTheDocument();
  });
});
