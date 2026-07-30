// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
//
// Dev-only installer for the app-level API mock. It reuses the playground mock
// as a base and layers larger-scale, higher-priority handlers so a full UI
// walkthrough renders realistic data. Imported only from the dev mock switch
// (behind import.meta.env.DEV), so none of this ships to production.
import type AxiosMockAdapter from 'axios-mock-adapter';
import camelcaseKeys from 'camelcase-keys';
import {
  FIXTURE_TIMESTAMP,
  fixtureConnectionFields,
  fixtureDingtalkGroupConfigItems,
} from '../../playground/fixtures';
import { installPlaygroundApiMock } from '../../playground/mockApi';
import type { PlaygroundFixtureProfile } from '../../playground/types';
import type { AlertRuleItem } from '../../types/alerts';
import type { InvestmentFrameworkContent } from '../../types/investmentFramework';
import type { SystemConfigItem } from '../../types/systemConfig';
import {
  richAlertNotifications,
  richAlertRules,
  richAlertTriggers,
  richDecisionOutcomes,
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

const READY_FRAMEWORK_CONTENT: InvestmentFrameworkContent = {
  schemaVersion: 'investment-framework-content-v1',
  title: 'Quality compounder framework',
  description: 'A deterministic fixture for structured editing and immutable-history review.',
  rootNodeId: 'business_quality',
  decisionTree: [
    {
      nodeId: 'business_quality',
      question: 'Does the business have a durable moat and understandable economics?',
      branches: [
        { condition: 'Yes', targetNodeId: 'valuation' },
        { condition: 'No', outcome: 'Reject' },
      ],
    },
    {
      nodeId: 'valuation',
      question: 'Does the expected return compensate for valuation and downside risk?',
      branches: [
        { condition: 'Yes', outcome: 'Eligible for sizing' },
        { condition: 'No', outcome: 'Watchlist only' },
      ],
    },
  ],
  evaluationDimensions: [
    {
      name: 'Business quality',
      weight: 60,
      criteria: ['Durable moat', 'Healthy reinvestment runway'],
      description: 'Assess durability before forecasting returns.',
    },
    {
      name: 'Valuation and risk',
      weight: 40,
      criteria: ['Downside protection', 'Expected return'],
      description: 'Require a margin of safety.',
    },
  ],
  riskRules: ['Do not average down when the thesis is invalidated.'],
  trackingCriteria: ['Quarterly moat evidence', 'Capital allocation discipline'],
  freeFormRules: 'Document the disconfirming evidence before opening a position.',
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

function toAlertRuleWireItem(item: AlertRuleItem): Record<string, unknown> {
  const {
    cooldownPolicy,
    notificationPolicy,
    ...wireItem
  } = item;
  return {
    ...wireItem,
    ...(cooldownPolicy !== undefined ? { cooldown_policy: cooldownPolicy } : {}),
    ...(notificationPolicy !== undefined ? { notification_policy: notificationPolicy } : {}),
  };
}

function registerPriorityHandlers(mock: AxiosMockAdapter, profile: PlaygroundFixtureProfile): void {
  const memoryFlags = new Map<number, { memorable: boolean; ignored: boolean }>(
    richDecisionSignals.map((signal, index) => [
      signal.id,
      {
        memorable: index % 4 === 1 || index % 4 === 3,
        ignored: index % 4 === 2 || index % 4 === 3,
      },
    ]),
  );

  mock.onGet('/api/v1/system/config').reply(() => reply(profile, {
    configVersion: 'dev-mock-v1',
    maskToken: '******',
    items: [...REAL_CONFIG_ITEMS, ...fixtureDingtalkGroupConfigItems],
    configuredNotificationChannels: ['email', 'feishu', 'webhook', 'dingtalk'],
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
  mock.onPost('/api/v1/system/config/rollback').reply(() => (
    profile === 'error'
      ? [503, ERROR_PAYLOAD]
      : [200, {
        success: true,
        config_version: 'dev-mock-v0',
        applied_count: 2,
        skipped_masked_count: 0,
        reload_triggered: true,
        updated_keys: ['SCHEDULE_TIME', 'DINGTALK_WEBHOOK_URL'],
        warnings: ['Dev mock rollback is deterministic and does not persist.'],
      }]
  ));
  mock.onPost('/api/v1/system/config/notification/test-channel').reply((config) => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    let body: Record<string, unknown> = {};
    if (typeof config.data === 'string') {
      body = JSON.parse(config.data) as Record<string, unknown>;
    } else if (config.data && typeof config.data === 'object') {
      body = config.data as Record<string, unknown>;
    }
    const channel = typeof body.channel === 'string' ? body.channel : 'unknown';
    return [200, {
      success: true,
      message: `Fixture ${channel} notification delivered.`,
      retryable: false,
      latency_ms: 32,
      attempts: [{
        channel,
        success: true,
        message: 'Delivered',
        stage: 'dispatch',
        retryable: false,
        latency_ms: 32,
        http_status: 200,
      }],
    }];
  });

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

  mock.onGet('/api/v1/investment-framework').reply(() => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    if (profile === 'empty') {
      return [404, { error: 'not_found', message: 'No investment framework exists.' }];
    }
    return [200, {
      framework_id: 1,
      scope: 'local',
      version: 3,
      active_version: 3,
      revision: 7,
      is_active: true,
      content: READY_FRAMEWORK_CONTENT,
      change_summary: 'Refined valuation branch and tracking criteria.',
      created_at: '2026-06-01T08:00:00Z',
      updated_at: '2026-07-29T08:00:00Z',
      version_created_at: '2026-07-29T08:00:00Z',
    }];
  });
  mock.onGet('/api/v1/investment-framework/history').reply(() => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    if (profile === 'empty') {
      return [404, { error: 'not_found', message: 'No investment framework exists.' }];
    }
    return [200, {
      framework_id: 1,
      latest_version: 3,
      active_version: 3,
      revision: 7,
      total: 3,
      items: [
        {
          version: 3,
          is_active: true,
          content: READY_FRAMEWORK_CONTENT,
          change_summary: 'Refined valuation branch and tracking criteria.',
          created_at: '2026-07-29T08:00:00Z',
        },
        {
          version: 2,
          is_active: false,
          content: {
            ...READY_FRAMEWORK_CONTENT,
            title: 'Quality and valuation framework v2',
            trackingCriteria: ['Quarterly moat evidence'],
          },
          change_summary: 'Added a valuation decision node.',
          created_at: '2026-07-10T08:00:00Z',
        },
        {
          version: 1,
          is_active: false,
          content: {
            ...READY_FRAMEWORK_CONTENT,
            title: 'Initial quality framework',
            decisionTree: READY_FRAMEWORK_CONTENT.decisionTree?.slice(0, 1),
            rootNodeId: 'business_quality',
          },
          change_summary: 'Initial framework.',
          created_at: '2026-06-01T08:00:00Z',
        },
      ],
    }];
  });

  mock.onGet('/api/v1/analysis/tasks').reply(() => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    const tasks = profile === 'empty' ? [] : richTasks;
    const pending = tasks.filter((task) => task.status === 'pending').length;
    const processing = tasks.filter((task) => task.status === 'processing').length;
    return [200, { total: tasks.length, pending, processing, tasks }];
  });

  mock.onGet('/api/v1/scheduled-tasks').reply(() => reply(profile, {
    total: 2,
    items: [
      {
        compatibility: 'supported',
        id: 'scheduled-brief-aapl',
        schema_version: 2,
        name: 'AAPL morning brief',
        task_type: 'research_brief',
        enabled: true,
        next_run_at: '2026-07-25T14:30:00Z',
        created_at: FIXTURE_TIMESTAMP,
        updated_at: FIXTURE_TIMESTAMP,
      },
      {
        compatibility: 'supported',
        id: 'scheduled-risk-msft',
        schema_version: 2,
        name: 'MSFT downside review',
        task_type: 'risk_check',
        enabled: false,
        next_run_at: null,
        created_at: FIXTURE_TIMESTAMP,
        updated_at: FIXTURE_TIMESTAMP,
      },
    ],
  }, {
    total: 0,
    items: [],
  }));
  mock.onGet(/\/api\/v1\/scheduled-tasks\/[^/]+\/runs$/).reply((config) => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    const taskId = String(config.url || '').split('/').at(-2) || 'scheduled-task';
    const items = profile === 'empty' ? [] : [
      {
        id: `${taskId}-run-success`,
        task_id: taskId,
        scheduled_for: '2026-07-29T14:30:00Z',
        status: 'succeeded',
        attempt_count: 1,
        dispatch_failure_count: 0,
        execution_task_ids: ['analysis-task-aapl-0729'],
        result_refs: ['report:aapl:2026-07-29'],
        notification_status: 'delivered',
        notification_channels: ['dingtalk'],
        notification_failed_channels: [],
        error_code: null,
        next_attempt_at: null,
        started_at: '2026-07-29T14:30:02Z',
        finished_at: '2026-07-29T14:31:18Z',
        created_at: '2026-07-29T14:30:00Z',
        updated_at: '2026-07-29T14:31:18Z',
      },
      {
        id: `${taskId}-run-failed`,
        task_id: taskId,
        scheduled_for: '2026-07-28T14:30:00Z',
        status: 'failed',
        attempt_count: 3,
        dispatch_failure_count: 1,
        execution_task_ids: ['analysis-task-aapl-0728'],
        result_refs: [],
        notification_status: 'partial_failure',
        notification_channels: ['email', 'dingtalk'],
        notification_failed_channels: ['email'],
        error_code: 'upstream_timeout',
        next_attempt_at: null,
        started_at: '2026-07-28T14:30:01Z',
        finished_at: '2026-07-28T14:35:00Z',
        created_at: '2026-07-28T14:30:00Z',
        updated_at: '2026-07-28T14:35:00Z',
      },
    ];
    const limit = Math.max(1, Number(config.params?.limit) || 10);
    return [200, { items: items.slice(0, limit), total: items.length }];
  });
  mock.onPost(/\/api\/v1\/scheduled-tasks\/[^/]+\/enable$/).reply((config) => {
    const id = String(config.url || '').split('/').slice(-2, -1)[0] || 'task';
    return reply(profile, {
      compatibility: 'supported',
      id,
      schema_version: 2,
      name: id,
      task_type: 'research_brief',
      enabled: true,
      next_run_at: FIXTURE_TIMESTAMP,
      created_at: FIXTURE_TIMESTAMP,
      updated_at: FIXTURE_TIMESTAMP,
    }, {
      compatibility: 'supported',
      id,
      schema_version: 2,
      name: id,
      task_type: 'research_brief',
      enabled: false,
      next_run_at: null,
      created_at: FIXTURE_TIMESTAMP,
      updated_at: FIXTURE_TIMESTAMP,
    });
  });
  mock.onPost(/\/api\/v1\/scheduled-tasks\/[^/]+\/disable$/).reply((config) => {
    const id = String(config.url || '').split('/').slice(-2, -1)[0] || 'task';
    return reply(profile, {
      compatibility: 'supported',
      id,
      schema_version: 2,
      name: id,
      task_type: 'research_brief',
      enabled: false,
      next_run_at: null,
      created_at: FIXTURE_TIMESTAMP,
      updated_at: FIXTURE_TIMESTAMP,
    }, {
      compatibility: 'supported',
      id,
      schema_version: 2,
      name: id,
      task_type: 'research_brief',
      enabled: false,
      next_run_at: null,
      created_at: FIXTURE_TIMESTAMP,
      updated_at: FIXTURE_TIMESTAMP,
    });
  });
  mock.onGet('/api/v1/scheduled-tasks/today').reply(() => reply(profile, {
    date: '2026-07-25',
    timezone: 'UTC',
    generated_at: FIXTURE_TIMESTAMP,
    total: 2,
    items: [
      {
        task: {
          compatibility: 'supported',
          id: 'scheduled-brief-aapl',
          schema_version: 2,
          name: 'AAPL morning brief',
          task_type: 'research_brief',
          enabled: true,
          next_run_at: '2026-07-25T14:30:00Z',
          created_at: FIXTURE_TIMESTAMP,
          updated_at: FIXTURE_TIMESTAMP,
        },
        scheduled_for: '2026-07-25T14:30:00Z',
        status: 'succeeded',
        run: {
          id: 'scheduled-run-brief-aapl',
          status: 'succeeded',
          error_code: null,
        },
      },
      {
        task: {
          compatibility: 'supported',
          id: 'scheduled-risk-msft',
          schema_version: 2,
          name: 'MSFT downside review',
          task_type: 'risk_check',
          enabled: true,
          next_run_at: '2026-07-25T10:00:00Z',
          created_at: FIXTURE_TIMESTAMP,
          updated_at: FIXTURE_TIMESTAMP,
        },
        scheduled_for: '2026-07-25T10:00:00Z',
        status: 'scheduled',
        run: null,
      },
    ],
  }, {
    date: '2026-07-25',
    timezone: 'UTC',
    generated_at: FIXTURE_TIMESTAMP,
    total: 0,
    items: [],
  }));

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
  mock.onGet('/api/v1/decision-signals/outcomes').reply((config) => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    if (profile === 'empty') return [200, { items: [], total: 0, page: 1, page_size: 20 }];
    const params = config.params ?? {};
    const signalId = Number(params.signal_id);
    const page = Math.max(1, Number(params.page) || 1);
    const pageSize = Math.max(1, Number(params.page_size) || 20);
    const filtered = richDecisionOutcomes.filter((item) => (
      (!Number.isInteger(signalId) || item.signalId === signalId)
      && (!params.horizon || item.horizon === params.horizon)
      && (!params.engine_version || item.engineVersion === params.engine_version)
      && (!params.eval_status || item.evalStatus === params.eval_status)
      && (!params.outcome || item.outcome === params.outcome)
    ));
    const offset = (page - 1) * pageSize;
    return [200, {
      items: filtered.slice(offset, offset + pageSize),
      total: filtered.length,
      page,
      page_size: pageSize,
    }];
  });
  mock.onGet('/api/v1/decision-signals/outcomes/stats').reply(() => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    const outcomes = profile === 'empty' ? [] : richDecisionOutcomes;
    const completed = outcomes.filter((item) => item.evalStatus === 'completed');
    const hit = completed.filter((item) => item.outcome === 'hit').length;
    const returns = completed.flatMap((item) => (
      typeof item.stockReturnPct === 'number' ? [item.stockReturnPct] : []
    ));
    return [200, {
      engine_version: 'fixture-v2',
      horizons: null,
      statuses: ['active', 'expired'],
      total: outcomes.length,
      completed: completed.length,
      unable: outcomes.length - completed.length,
      hit,
      miss: completed.filter((item) => item.outcome === 'miss').length,
      neutral: completed.filter((item) => item.outcome === 'neutral').length,
      hit_rate_pct: completed.length > 0 ? (hit / completed.length) * 100 : null,
      avg_stock_return_pct: returns.length > 0
        ? returns.reduce((sum, value) => sum + value, 0) / returns.length
        : null,
      unable_reasons: outcomes.length > completed.length
        ? { insufficient_price_history: outcomes.length - completed.length }
        : {},
      breakdowns: {},
    }];
  });
  mock.onGet(/\/api\/v1\/decision-signals\/\d+$/).reply((config) => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    const signalId = Number(String(config.url || '').split('/').at(-1));
    const item = richDecisionSignals.find((signal) => signal.id === signalId);
    return item ? [200, item] : [404, { error: 'not_found', message: 'Decision signal not found.' }];
  });
  mock.onGet(/\/api\/v1\/decision-signals\/\d+\/outcomes$/).reply((config) => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    const signalId = Number(String(config.url || '').split('/').at(-2));
    const items = profile === 'empty'
      ? []
      : richDecisionOutcomes.filter((item) => item.signalId === signalId);
    return [200, { items, total: items.length, page: 1, page_size: 20 }];
  });
  mock.onGet(/\/api\/v1\/decision-signals\/\d+\/feedback$/).reply((config) => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    const signalId = Number(String(config.url || '').split('/').at(-2));
    return [200, {
      signal_id: signalId,
      feedback_value: null,
      reason_code: null,
      note: null,
      source: null,
      created_at: null,
      updated_at: null,
    }];
  });
  mock.onGet(/\/api\/v1\/decision-signals\/\d+\/memory-flag$/).reply((config) => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    const signalId = Number(String(config.url || '').split('/').at(-2));
    const flags = memoryFlags.get(signalId) ?? { memorable: false, ignored: false };
    return [200, {
      signal_id: signalId,
      ...flags,
      created_at: FIXTURE_TIMESTAMP,
      updated_at: FIXTURE_TIMESTAMP,
    }];
  });
  mock.onPatch(/\/api\/v1\/decision-signals\/\d+\/memory-flag$/).reply((config) => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    const signalId = Number(String(config.url || '').split('/').at(-2));
    const body = typeof config.data === 'string'
      ? JSON.parse(config.data) as Record<string, unknown>
      : {};
    const current = memoryFlags.get(signalId) ?? { memorable: false, ignored: false };
    const next = {
      memorable: typeof body.memorable === 'boolean' ? body.memorable : current.memorable,
      ignored: typeof body.ignored === 'boolean' ? body.ignored : current.ignored,
    };
    memoryFlags.set(signalId, next);
    return [200, {
      signal_id: signalId,
      ...next,
      created_at: FIXTURE_TIMESTAMP,
      updated_at: FIXTURE_TIMESTAMP,
    }];
  });

  mock.onGet('/api/v1/alerts/rules').reply(() => reply(profile, {
    items: richAlertRules.map(toAlertRuleWireItem),
    total: richAlertRules.length,
    page: 1,
    pageSize: 20,
  }, { items: [], total: 0, page: 1, pageSize: 20 }));
  mock.onGet(/\/api\/v1\/alerts\/rules\/\d+$/).reply((config) => {
    if (profile === 'error') return [503, ERROR_PAYLOAD];
    const ruleId = Number(String(config.url || '').split('/').at(-1));
    const item = richAlertRules.find((rule) => rule.id === ruleId);
    return item
      ? [200, toAlertRuleWireItem(item)]
      : [404, { error: 'not_found', message: 'Alert rule not found.' }];
  });
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
