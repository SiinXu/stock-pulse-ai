// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SettingsSectionNav, SettingsViewTabs } from '../SettingsNavigation';

describe('SettingsSectionNav', () => {
  it('renders all sections and marks the active one', () => {
    render(
      <SettingsSectionNav
        activeSection="ai_models"
        onSelectSection={() => {}}
        language="zh"
        navLabel="设置导航"
      />,
    );
    const aiButton = screen.getByRole('button', { name: /AI 与模型/ });
    expect(aiButton).toHaveAttribute('aria-current', 'page');
    expect(aiButton).toHaveClass('min-h-11');
    // A non-active section is present without aria-current.
    const dataButton = screen.getByRole('button', { name: /数据源/ });
    expect(dataButton).not.toHaveAttribute('aria-current');
  });

  it('invokes onSelectSection with the section id', () => {
    const onSelect = vi.fn();
    render(
      <SettingsSectionNav
        activeSection="ai_models"
        onSelectSection={onSelect}
        language="en"
        navLabel="Settings navigation"
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Notifications/ }));
    expect(onSelect).toHaveBeenCalledWith('notifications');
  });

  it('offers a compact select for the short mobile path', () => {
    const onSelect = vi.fn();
    render(
      <SettingsSectionNav
        activeSection="ai_models"
        onSelectSection={onSelect}
        language="zh"
        navLabel="设置导航"
      />,
    );
    const select = screen.getByRole('combobox', { name: '设置导航' });
    expect(select).toHaveValue('ai_models');
    expect(select).toHaveClass('min-h-11');
    // Every section is reachable in one tap from the current section.
    expect(within(select).getAllByRole('option')).toHaveLength(11);
    fireEvent.change(select, { target: { value: 'notifications' } });
    expect(onSelect).toHaveBeenCalledWith('notifications');
  });

  it('prefers the mobile-specific handler for the compact selector when provided', () => {
    const onSelect = vi.fn();
    const onMobileSelect = vi.fn();
    render(
      <SettingsSectionNav
        activeSection="ai_models"
        onSelectSection={onSelect}
        onMobileSelectSection={onMobileSelect}
        language="zh"
        navLabel="设置导航"
      />,
    );
    fireEvent.change(screen.getByRole('combobox', { name: '设置导航' }), {
      target: { value: 'reports' },
    });
    // The mobile selector routes through the focus-shifting handler, not the
    // plain desktop one.
    expect(onMobileSelect).toHaveBeenCalledWith('reports');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('shows a status dot (state only, never counts) with an accessible label', () => {
    render(
      <SettingsSectionNav
        activeSection="ai_models"
        onSelectSection={() => {}}
        sectionStatus={{
          ai_models: { hasError: true },
          data_sources: { isDirty: true },
          notifications: { needsAction: true },
        }}
        language="zh"
        navLabel="设置导航"
      />,
    );
    expect(screen.getByRole('img', { name: '有错误' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: '有未保存修改' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: '需要操作' })).toBeInTheDocument();
    // No numeric field counts leak into the nav.
    expect(screen.queryByText(/\d+/)).not.toBeInTheDocument();
  });
});

describe('SettingsViewTabs', () => {
  it('renders the four AI & Models views and marks the active tab', () => {
    render(
      <SettingsViewTabs
        section="ai_models"
        activeView="task_routing"
        onSelectView={() => {}}
        language="en"
        tabsLabel="AI & Models views"
      />,
    );
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      'Overview',
      'Model Access',
      'Task Routing',
      'Reliability',
    ]);
    expect(screen.getByRole('tab', { name: 'Task Routing' })).toHaveAttribute('aria-selected', 'true');
    for (const tab of tabs) {
      expect(tab).toHaveClass('min-h-11');
    }
  });

  it('invokes onSelectView with the view id', () => {
    const onSelect = vi.fn();
    render(
      <SettingsViewTabs
        section="ai_models"
        activeView="connections"
        onSelectView={onSelect}
        language="zh"
        tabsLabel="AI 视图"
      />,
    );
    fireEvent.click(screen.getByRole('tab', { name: '可靠性' }));
    expect(onSelect).toHaveBeenCalledWith('reliability');
  });

  it('renders nothing for a single-view section', () => {
    const { container } = render(
      <SettingsViewTabs
        section="notifications"
        activeView="channels"
        onSelectView={() => {}}
        language="en"
        tabsLabel="views"
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
