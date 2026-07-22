// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
//
// Dev-only installer for the app-level API mock. It reuses the playground mock
// as a base and layers larger-scale, higher-priority handlers so a full UI
// walkthrough renders realistic data. Imported only from the dev mock switch
// (behind import.meta.env.DEV), so none of this ships to production.
import type AxiosMockAdapter from 'axios-mock-adapter';
import camelcaseKeys from 'camelcase-keys';
import { FIXTURE_TIMESTAMP, fixtureConnectionFields } from '../../playground/fixtures';
import { installPlaygroundApiMock } from '../../playground/mockApi';
import type { PlaygroundFixtureProfile } from '../../playground/types';
import type { SystemConfigItem } from '../../types/systemConfig';
import {
  richAlertNotifications,
  richAlertRules,
  richAlertTriggers,
  richDecisionSignals,
  richHistoryItems,
  richIntelligenceItems,
  richIntelligenceSources,
  richProviders,
  richStockBarItems,
  richTasks,
} from './fixtures';
import { REAL_SYSTEM_CONFIG, REAL_SYSTEM_CONFIG_SCHEMA } from './systemConfigFixture';

// The API layer camel-cases responses, so the captured snake_case payloads are
// normalized here the same way to match the app's SystemConfigItem shape.
const realConfig = camelcaseKeys(REAL_SYSTEM_CONFIG as Record<string, unknown>, { deep: true }) as {
  items?: SystemConfigItem[];
};
const REAL_CONFIG_ITEMS: SystemConfigItem[] = realConfig.items ?? [];
const REAL_CONFIG_SCHEMA = camelcaseKeys(REAL_SYSTEM_CONFIG_SCHEMA as Record<string, unknown>, { deep: true }) as {
  schemaVersion?: string;
  categories: unknown[];
};

const ERROR_PAYLOAD = {
  error: 'dev_mock_error',
  message: 'The selected dev mock profile returns a deterministic service error.',
};

type MockReply = [number, unknown];

function reply(profile: PlaygroundFixtureProfile, ready: unknown, empty: unknown): MockReply {
  if (profile === 'error') return [503, ERROR_PAYLOAD];
  return [200, profile === 'empty' ? empty : ready];
}

function registerPriorityHandlers(mock: AxiosMockAdapter, profile: PlaygroundFixtureProfile): void {
  mock.onGet('/api/v1/system/config').reply(() => reply(profile, {
    configVersion: 'dev-mock-v1',
    maskToken: '******',
    items: REAL_CONFIG_ITEMS,
    configuredNotificationChannels: ['email', 'feishu', 'webhook'],
    updatedAt: FIXTURE_TIMESTAMP,
  }, {
    configVersion: 'dev-mock-v1',
    maskToken: '******',
    items: [],
    configuredNotificationChannels: [],
    updatedAt: FIXTURE_TIMESTAMP,
  }));
  mock.onGet('/api/v1/system/config/schema').reply(() => reply(profile, {
    schemaVersion: REAL_CONFIG_SCHEMA.schemaVersion ?? 'dev-mock-v1',
    categories: REAL_CONFIG_SCHEMA.categories,
  }, { schemaVersion: 'dev-mock-v1', categories: [] }));
  mock.onPut('/api/v1/system/config').reply(() => (profile === 'error' ? [503, ERROR_PAYLOAD] : [200, {
    success: true,
    configVersion: 'dev-mock-v2',
    appliedCount: 0,
    skippedMaskedCount: 0,
    reloadTriggered: false,
    updatedKeys: [],
    warnings: ['Dev mock does not persist configuration edits.'],
  }]));

  mock.onGet('/api/v1/system/config/llm/providers').reply(() => reply(profile, {
    providers: richProviders,
    connectionFields: fixtureConnectionFields,
    emptyApiKeyHosts: [],
  }, { providers: [], connectionFields: [], emptyApiKeyHosts: [] }));

  mock.onGet('/api/v1/history').reply(() => reply(profile, {
    total: richHistoryItems.length,
    page: 1,
    limit: 20,
    items: richHistoryItems,
  }, { total: 0, page: 1, limit: 20, items: [] }));
  mock.onGet('/api/v1/history/stocks').reply(() => reply(profile, {
    total: richStockBarItems.length,
    items: richStockBarItems,
  }, { total: 0, items: [] }));

  mock.onGet('/api/v1/analysis/tasks').reply(() => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    const tasks = profile === 'empty' ? [] : richTasks;
    const pending = tasks.filter((task) => task.status === 'pending').length;
    const processing = tasks.filter((task) => task.status === 'processing').length;
    return [200, { total: tasks.length, pending, processing, tasks }];
  });

  mock.onGet('/api/v1/agent/skills').reply(() => reply(profile, {
    skills: [
      { id: 'analysis', name: 'Equity analysis', description: 'End-to-end single-stock analysis pipeline.' },
      { id: 'market_review', name: 'Market review', description: 'Breadth, sectors and concept rotation summary.' },
      { id: 'screening', name: 'Screening', description: 'Rule-based candidate screening over the universe.' },
      { id: 'deep_research', name: 'Deep research', description: 'Multi-step research with cited sources.' },
    ],
    default_skill_id: 'analysis',
  }, { skills: [], default_skill_id: '' }));

  mock.onGet('/api/v1/decision-signals').reply(() => reply(profile, {
    items: richDecisionSignals,
    total: richDecisionSignals.length,
    page: 1,
    page_size: 20,
  }, { items: [], total: 0, page: 1, page_size: 20 }));

  mock.onGet('/api/v1/alerts/rules').reply(() => reply(profile, {
    items: richAlertRules,
    total: richAlertRules.length,
    page: 1,
    pageSize: 20,
  }, { items: [], total: 0, page: 1, pageSize: 20 }));
  mock.onGet('/api/v1/alerts/triggers').reply(() => reply(profile, {
    items: richAlertTriggers,
    total: richAlertTriggers.length,
    page: 1,
    pageSize: 20,
  }, { items: [], total: 0, page: 1, pageSize: 20 }));
  mock.onGet('/api/v1/alerts/notifications').reply(() => reply(profile, {
    items: richAlertNotifications,
    total: richAlertNotifications.length,
    page: 1,
    pageSize: 20,
  }, { items: [], total: 0, page: 1, pageSize: 20 }));

  mock.onGet('/api/v1/intelligence/sources').reply(() => reply(profile, {
    items: richIntelligenceSources,
    total: richIntelligenceSources.length,
    page: 1,
    page_size: 100,
  }, { items: [], total: 0, page: 1, page_size: 100 }));
  mock.onGet('/api/v1/intelligence/items').reply(() => reply(profile, {
    items: richIntelligenceItems,
    total: richIntelligenceItems.length,
    page: 1,
    page_size: 20,
  }, { items: [], total: 0, page: 1, page_size: 20 }));
}

export function installAppApiMock(profile: PlaygroundFixtureProfile) {
  return installPlaygroundApiMock(profile, { registerPriorityHandlers });
}
