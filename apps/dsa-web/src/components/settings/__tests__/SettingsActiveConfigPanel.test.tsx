// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ComponentProps } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { SystemConfigCategory, SystemConfigItem } from '../../../types/systemConfig';
import SettingsActiveConfigPanel from '../SettingsActiveConfigPanel';
import {
  getCategoryFieldGroupId,
  getCategoryFieldGroupOrder,
  getCategoryFieldOrder,
} from '../categoryFieldGroups';
import {
  NOTIFICATION_FIELD_GROUP_ORDER,
  getNotificationFieldGroupId,
  getNotificationFieldOrder,
} from '../notificationFieldGroups';
import { SETTINGS_DEFAULT_OPEN_GROUP_IDS } from '../settingsFieldGroupDisclosure';

function configItem(
  key: string,
  category: SystemConfigCategory,
  title = key,
): SystemConfigItem {
  return {
    key,
    value: '1',
    rawValueExists: true,
    isMasked: false,
    schema: {
      key,
      title,
      category,
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

function renderPanel(overrides: Partial<ComponentProps<typeof SettingsActiveConfigPanel>> = {}) {
  const items = overrides.subFilteredItems ?? [
    configItem('REALTIME_SOURCE_PRIORITY', 'data_source', 'Quote priority'),
    configItem('TAVILY_API_KEYS', 'data_source', 'Tavily keys'),
    configItem('NEWS_MAX_AGE_DAYS', 'data_source', 'News age'),
    configItem('UNMAPPED_DATA_KEY', 'data_source', 'Unmapped data'),
  ];
  return render(
    <UiLanguageProvider initialLanguage="en">
      <SettingsActiveConfigPanel
        panelKey="data_sources:sources"
        title="Data sources"
        description="Sources"
        shouldRender
        showEmptyState={false}
        isNotificationChannelsSub={false}
        isDataProvidersSub={false}
        visibleActiveItems={items}
        subFilteredItems={items}
        activeSubPromptCacheItems={[]}
        activeFieldGroupOrder={getCategoryFieldGroupOrder('data_source')}
        fieldGroupIdOf={(key) => getCategoryFieldGroupId('data_source', key)}
        fieldGroupOrderOf={(key) => getCategoryFieldOrder('data_source', key)}
        configuredNotificationChannels={[]}
        hasConfiguredNotificationChannelStatus={false}
        configuredRoutingValues={new Set()}
        channelRoutingFieldKeys={new Set()}
        channelRoutingEmptyBanner={null}
        channelRoutingEmptyState={null}
        channelRoutingOptionFilter={() => true}
        isSaving={false}
        issueByKey={{}}
        allValuesByKey={Object.fromEntries(items.map((item) => [item.key, item.value]))}
        persistedValuesByKey={Object.fromEntries(items.map((item) => [item.key, item.value]))}
        alphasiftEnabled={false}
        setDraftValue={vi.fn()}
        applyPartialUpdate={vi.fn()}
        resetDraftKeys={vi.fn()}
        activeSaveStatus="idle"
        agentModelSummary={{ value: '', source: 'inherited', readiness: 'unconfigured' }}
        readOnlyDiagnosticForItem={() => undefined}
        activeCategory="data_source"
        configVersion="v1"
        {...overrides}
      />
    </UiLanguageProvider>,
  );
}

async function groupToggle(groupId: string): Promise<HTMLElement> {
  const group = await screen.findByTestId(`settings-field-group-${groupId}`);
  return group.querySelector('button[aria-expanded]') as HTMLElement;
}

describe('SettingsActiveConfigPanel group disclosure', () => {
  it('defaults open only quote, primary, and schedule among non-empty groups', async () => {
    expect([...SETTINGS_DEFAULT_OPEN_GROUP_IDS]).toEqual(['quote', 'primary', 'schedule']);

    const data = renderPanel();
    expect(await groupToggle('quote')).toHaveAttribute('aria-expanded', 'true');
    expect(await groupToggle('search')).toHaveAttribute('aria-expanded', 'false');
    expect(await groupToggle('news')).toHaveAttribute('aria-expanded', 'false');
    expect(await groupToggle('other')).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('settings-field-group-providerReliability')).not.toBeInTheDocument();
    data.unmount();

    const aiItems = [
      configItem('LITELLM_MODEL', 'ai_model', 'Primary model'),
      configItem('GENERATION_BACKEND', 'ai_model', 'Backend'),
    ];
    const ai = renderPanel({
      panelKey: 'ai_models:reliability',
      activeCategory: 'ai_model',
      subFilteredItems: aiItems,
      visibleActiveItems: aiItems,
      activeFieldGroupOrder: getCategoryFieldGroupOrder('ai_model'),
      fieldGroupIdOf: (key) => getCategoryFieldGroupId('ai_model', key),
      fieldGroupOrderOf: (key) => getCategoryFieldOrder('ai_model', key),
      allValuesByKey: Object.fromEntries(aiItems.map((item) => [item.key, item.value])),
      persistedValuesByKey: Object.fromEntries(aiItems.map((item) => [item.key, item.value])),
    });
    expect(await groupToggle('primary')).toHaveAttribute('aria-expanded', 'true');
    expect(await groupToggle('backend')).toHaveAttribute('aria-expanded', 'false');
    ai.unmount();

    const systemItems = [
      configItem('SCHEDULE_ENABLED', 'system', 'Schedule enabled'),
      configItem('WEBUI_PORT', 'system', 'Web port'),
    ];
    renderPanel({
      panelKey: 'system_security:runtime',
      activeCategory: 'system',
      subFilteredItems: systemItems,
      visibleActiveItems: systemItems,
      activeFieldGroupOrder: getCategoryFieldGroupOrder('system'),
      fieldGroupIdOf: (key) => getCategoryFieldGroupId('system', key),
      fieldGroupOrderOf: (key) => getCategoryFieldOrder('system', key),
      allValuesByKey: Object.fromEntries(systemItems.map((item) => [item.key, item.value])),
      persistedValuesByKey: Object.fromEntries(systemItems.map((item) => [item.key, item.value])),
    });
    expect(await groupToggle('schedule')).toHaveAttribute('aria-expanded', 'true');
    expect(await groupToggle('web')).toHaveAttribute('aria-expanded', 'false');
  });

  it('reveals a collapsed group when search or a deep link targets a field inside it', async () => {
    const { rerender } = renderPanel();
    expect(await groupToggle('search')).toHaveAttribute('aria-expanded', 'false');

    const items = [
      configItem('REALTIME_SOURCE_PRIORITY', 'data_source', 'Quote priority'),
      configItem('TAVILY_API_KEYS', 'data_source', 'Tavily keys'),
      configItem('NEWS_MAX_AGE_DAYS', 'data_source', 'News age'),
      configItem('UNMAPPED_DATA_KEY', 'data_source', 'Unmapped data'),
    ];
    rerender(
      <UiLanguageProvider initialLanguage="en">
        <SettingsActiveConfigPanel
          panelKey="data_sources:sources"
          title="Data sources"
          description="Sources"
          shouldRender
          showEmptyState={false}
          isNotificationChannelsSub={false}
          isDataProvidersSub={false}
          visibleActiveItems={items}
          subFilteredItems={items}
          activeSubPromptCacheItems={[]}
          activeFieldGroupOrder={getCategoryFieldGroupOrder('data_source')}
          fieldGroupIdOf={(key) => getCategoryFieldGroupId('data_source', key)}
          fieldGroupOrderOf={(key) => getCategoryFieldOrder('data_source', key)}
          configuredNotificationChannels={[]}
          hasConfiguredNotificationChannelStatus={false}
          configuredRoutingValues={new Set()}
          channelRoutingFieldKeys={new Set()}
          channelRoutingEmptyBanner={null}
          channelRoutingEmptyState={null}
          channelRoutingOptionFilter={() => true}
          isSaving={false}
          issueByKey={{}}
          allValuesByKey={Object.fromEntries(items.map((item) => [item.key, item.value]))}
          persistedValuesByKey={Object.fromEntries(items.map((item) => [item.key, item.value]))}
          alphasiftEnabled={false}
          setDraftValue={vi.fn()}
          applyPartialUpdate={vi.fn()}
          resetDraftKeys={vi.fn()}
          activeSaveStatus="idle"
          agentModelSummary={{ value: '', source: 'inherited', readiness: 'unconfigured' }}
          readOnlyDiagnosticForItem={() => undefined}
          activeCategory="data_source"
          configVersion="v1"
          revealFieldKey="TAVILY_API_KEYS"
        />
      </UiLanguageProvider>,
    );

    expect(await groupToggle('search')).toHaveAttribute('aria-expanded', 'true');
    expect(await groupToggle('news')).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByTestId('settings-field-TAVILY_API_KEYS')).toBeInTheDocument();
  });

  it('wraps notification groups and keeps them collapsed by default', async () => {
    const items = [
      configItem('NOTIFICATION_REPORT_CHANNELS', 'notification', 'Report channels'),
      configItem('REPORT_TYPE', 'notification', 'Report type'),
      configItem('UNMAPPED_NOTIFY', 'notification', 'Other notify'),
    ];
    renderPanel({
      panelKey: 'alerts:routing',
      activeCategory: 'notification',
      subFilteredItems: items,
      visibleActiveItems: items,
      activeFieldGroupOrder: NOTIFICATION_FIELD_GROUP_ORDER,
      fieldGroupIdOf: getNotificationFieldGroupId,
      fieldGroupOrderOf: getNotificationFieldOrder,
      allValuesByKey: Object.fromEntries(items.map((item) => [item.key, item.value])),
      persistedValuesByKey: Object.fromEntries(items.map((item) => [item.key, item.value])),
    });

    expect(await groupToggle('routing')).toHaveAttribute('aria-expanded', 'false');
    expect(await groupToggle('report')).toHaveAttribute('aria-expanded', 'false');
    expect(await groupToggle('other')).toHaveAttribute('aria-expanded', 'false');
  });

  it('exposes aria-expanded and aria-controls on each group toggle', async () => {
    renderPanel();
    const searchToggle = await groupToggle('search');
    expect(searchToggle).toHaveAttribute('type', 'button');
    expect(searchToggle).toHaveAttribute('aria-expanded', 'false');
    const panelId = searchToggle.getAttribute('aria-controls');
    expect(panelId).toBeTruthy();
    const panel = document.getElementById(panelId!);
    expect(panel).toBeInstanceOf(HTMLElement);
    expect(panel).toHaveAttribute('hidden');
    expect(panel).toHaveAttribute('inert');
    fireEvent.click(searchToggle);
    expect(searchToggle).toHaveAttribute('aria-expanded', 'true');
    expect(panel).not.toHaveAttribute('hidden');
    expect(panel).not.toHaveAttribute('inert');
  });
});
