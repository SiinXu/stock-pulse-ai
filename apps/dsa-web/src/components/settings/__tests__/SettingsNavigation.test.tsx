// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
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
    expect(select).toHaveAttribute('data-value', 'ai_models');
    expect(select).toHaveClass('min-h-11');
    // Every section is reachable in one tap from the current section.
    fireEvent.click(select);
    expect(screen.getAllByRole('option')).toHaveLength(12);
    fireEvent.click(screen.getByRole('option', { name: '通知' }));
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
    fireEvent.click(screen.getByRole('combobox', { name: '设置导航' }));
    fireEvent.click(screen.getByRole('option', { name: '报告' }));
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

  it('hides advanced sections in beginner mode and offers a reveal', () => {
    const onReveal = vi.fn();
    render(
      <SettingsSectionNav
        activeSection="ai_models"
        onSelectSection={() => {}}
        language="en"
        navLabel="Settings navigation"
        beginnerMode
        advancedRevealed={false}
        onRevealAdvanced={onReveal}
      />,
    );
    // Essential sections stay; an advanced one (Backtesting) is hidden.
    expect(screen.getByRole('button', { name: /AI & Models/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Backtesting/ })).not.toBeInTheDocument();
    const revealButtons = screen.getAllByRole('button', { name: 'Show advanced settings' });
    fireEvent.click(revealButtons[0]);
    expect(onReveal).toHaveBeenCalledTimes(1);
  });

  it('limits the mobile selector to essential sections in beginner mode', () => {
    render(
      <SettingsSectionNav
        activeSection="ai_models"
        onSelectSection={() => {}}
        language="zh"
        navLabel="设置导航"
        beginnerMode
        advancedRevealed={false}
        onRevealAdvanced={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole('combobox', { name: '设置导航' }));
    // Only the four essentials: Overview, AI & Models, Data Sources, Notifications.
    expect(screen.getAllByRole('option')).toHaveLength(4);
  });

  it('keeps the active advanced section reachable in beginner mode', () => {
    render(
      <SettingsSectionNav
        activeSection="backtesting"
        onSelectSection={() => {}}
        language="en"
        navLabel="Settings navigation"
        beginnerMode
        advancedRevealed={false}
        onRevealAdvanced={() => {}}
      />,
    );
    expect(screen.getByRole('button', { name: /Backtesting/ })).toHaveAttribute('aria-current', 'page');
  });

  it('shows every section and no reveal once advanced is revealed', () => {
    render(
      <SettingsSectionNav
        activeSection="ai_models"
        onSelectSection={() => {}}
        language="en"
        navLabel="Settings navigation"
        beginnerMode
        advancedRevealed
        onRevealAdvanced={() => {}}
      />,
    );
    expect(screen.getByRole('button', { name: /Backtesting/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Show advanced settings' })).not.toBeInTheDocument();
  });
});

describe('SettingsViewTabs', () => {
  it('renders the five AI & Models views and marks the active tab', () => {
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
      'Local Models',
      'Task Routing',
      'Reliability',
    ]);
    expect(screen.getByRole('tab', { name: 'Task Routing' })).toHaveAttribute('aria-selected', 'true');
    for (const tab of tabs) {
      expect(tab).toHaveClass('min-h-6', 'segmented-control-tab');
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
