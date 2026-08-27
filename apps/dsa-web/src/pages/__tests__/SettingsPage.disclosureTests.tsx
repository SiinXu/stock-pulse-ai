// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import SettingsPageTestHarness from './SettingsPage.testHarness';

const {
  SettingsPage,
  buildSystemConfigState,
  routerSearchParamsMock,
  useSystemConfigMock,
} = SettingsPageTestHarness;

function dataSourceItems() {
  return [
    {
      key: 'REALTIME_SOURCE_PRIORITY',
      value: 'tencent',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'REALTIME_SOURCE_PRIORITY',
        title: 'Quote priority',
        category: 'data_source' as const,
        dataType: 'string' as const,
        uiControl: 'text' as const,
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
      },
    },
    {
      key: 'TAVILY_API_KEYS',
      value: '',
      rawValueExists: false,
      isMasked: false,
      schema: {
        key: 'TAVILY_API_KEYS',
        title: 'Tavily keys',
        category: 'data_source' as const,
        dataType: 'string' as const,
        uiControl: 'password' as const,
        isSensitive: true,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 2,
      },
    },
  ];
}

function mountDataSources(extraSearch?: Record<string, string>) {
  const configState = buildSystemConfigState();
  useSystemConfigMock.mockReturnValue(buildSystemConfigState({
    activeCategory: 'data_source',
    activeSubCategory: 'source',
    itemsByCategory: {
      ...configState.itemsByCategory,
      data_source: dataSourceItems(),
    },
    issueByKey: extraSearch?.withError === '1'
      ? {
          TAVILY_API_KEYS: [{
            key: 'TAVILY_API_KEYS',
            code: 'required',
            message: 'Tavily required',
            severity: 'error',
          }],
        }
      : {},
  }));
  const params = new URLSearchParams({
    section: 'data_sources',
    view: 'sources',
    ...extraSearch,
  });
  params.delete('withError');
  routerSearchParamsMock.params = params;
  render(<SettingsPage />);
}

async function groupToggle(groupId: string): Promise<HTMLElement> {
  const group = await screen.findByTestId(`settings-field-group-${groupId}`);
  return group.querySelector('button[aria-expanded]') as HTMLElement;
}

export function registerSettingsPageDisclosureTests(): void {
  it('opens quote by default and keeps search collapsed until a field deep link arrives', async () => {
    mountDataSources();
    expect(await groupToggle('quote')).toHaveAttribute('aria-expanded', 'true');
    expect(await groupToggle('search')).toHaveAttribute('aria-expanded', 'false');
    expect(await screen.findByTestId('settings-field-TAVILY_API_KEYS')).toBeInTheDocument();
  });

  it('reveals a collapsed group when a field query targets it', async () => {
    mountDataSources({ field: 'TAVILY_API_KEYS' });
    expect(await groupToggle('search')).toHaveAttribute('aria-expanded', 'true');
    expect(await groupToggle('quote')).toHaveAttribute('aria-expanded', 'true');
  });

  it('reveals a collapsed group when the validation summary jumps to a field', async () => {
    mountDataSources({ withError: '1' });
    expect(await groupToggle('search')).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(screen.getByRole('button', { name: /前往修正: Tavily API Keys/ }));
    expect(await groupToggle('search')).toHaveAttribute('aria-expanded', 'true');
  });

  it('opens Web & Logs groups on direct service entry so diagnostics controls are reachable', async () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      activeSubCategory: 'web',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          {
            key: 'WEBUI_PORT',
            value: '8000',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'WEBUI_PORT',
              title: 'Web UI Port',
              category: 'system' as const,
              dataType: 'integer' as const,
              uiControl: 'number' as const,
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: { min: 1, max: 65535 },
              displayOrder: 1,
            },
          },
          {
            key: 'LOG_LEVEL',
            value: 'INFO',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'LOG_LEVEL',
              title: '日志级别',
              category: 'system' as const,
              dataType: 'string' as const,
              uiControl: 'select' as const,
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
              validation: {},
              displayOrder: 2,
            },
          },
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({
      section: 'system_security',
      view: 'service',
    });
    render(<SettingsPage />);

    expect(await groupToggle('web')).toHaveAttribute('aria-expanded', 'true');
    expect(await groupToggle('log')).toHaveAttribute('aria-expanded', 'true');
    const logLevel = await screen.findByRole('combobox', { name: '日志级别' });
    expect(logLevel.closest('[hidden]')).toBeNull();
    expect(logLevel.closest('[inert]')).toBeNull();
  });

  it('keeps Event Monitor expert JSON behind a default-closed Collapsible', async () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'agent',
      itemsByCategory: {
        ...configState.itemsByCategory,
        agent: [
          {
            key: 'AGENT_EVENT_MONITOR_ENABLED',
            value: 'false',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_EVENT_MONITOR_ENABLED',
              title: 'Event monitor enabled',
              category: 'agent' as const,
              dataType: 'boolean' as const,
              uiControl: 'switch' as const,
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 1,
            },
          },
          {
            key: 'AGENT_EVENT_ALERT_RULES_JSON',
            value: '{}',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_EVENT_ALERT_RULES_JSON',
              title: 'Event alert rules JSON',
              category: 'agent' as const,
              dataType: 'string' as const,
              uiControl: 'textarea' as const,
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 2,
            },
          },
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({
      section: 'alerts',
      view: 'events',
    });
    render(<SettingsPage />);

    const chrome = await screen.findByTestId('event-monitor-expert-json');
    const toggle = chrome.querySelector('button[aria-expanded]') as HTMLElement;
    expect(toggle).toHaveAttribute('type', 'button');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    const panelId = toggle.getAttribute('aria-controls');
    expect(panelId).toBeTruthy();
    const panel = document.getElementById(panelId!);
    expect(panel).toHaveAttribute('hidden');
    expect(panel).toHaveAttribute('inert');
    expect(screen.getByTestId('event-monitor-essentials')).toBeInTheDocument();
    expect(screen.getByTestId('settings-field-AGENT_EVENT_ALERT_RULES_JSON').closest('[hidden]')).toBeTruthy();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(panel).not.toHaveAttribute('hidden');
    expect(screen.getByTestId('settings-field-AGENT_EVENT_ALERT_RULES_JSON').closest('[hidden]')).toBeNull();
  });
}
