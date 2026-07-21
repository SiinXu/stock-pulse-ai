import type { AxiosError, InternalAxiosRequestConfig } from 'axios';
import AxiosMockAdapter from 'axios-mock-adapter';
import apiClient from '../api';
import {
  FIXTURE_TIMESTAMP,
  fixtureAlertRules,
  fixtureAlertTriggers,
  fixtureConnectionFields,
  fixtureDecisionOutcome,
  fixtureDecisionSignal,
  fixtureDiagnosticSummary,
  fixtureHistoryItems,
  fixtureProviders,
  fixtureReport,
  fixtureRunFlowSnapshot,
  fixtureStockBarItems,
  fixtureSystemConfigItems,
} from './fixtures';
import type { PlaygroundFixtureProfile, PlaygroundRequestLog } from './types';

type TimedRequestConfig = InternalAxiosRequestConfig & {
  __playgroundRequestId?: string;
  __playgroundStartedAt?: number;
};

type InstallPlaygroundApiMockOptions = {
  onRequestLog?: (event: PlaygroundRequestLog) => void;
  delayResponse?: number;
};

type MockState = {
  configVersion: number;
  configItems: typeof fixtureSystemConfigItems;
  watchlist: string[];
  alertRules: typeof fixtureAlertRules;
  decisionSignals: Array<typeof fixtureDecisionSignal>;
  intelligenceSources: IntelligenceSourceFixture[];
  authStatus: {
    authEnabled: boolean;
    loggedIn: boolean;
    passwordSet: boolean;
    passwordChangeable: boolean;
    setupState: 'enabled' | 'password_retained' | 'no_password';
  };
};

type IntelligenceSourceFixture = {
  id: number;
  name: string;
  sourceType: string;
  url: string;
  enabled: boolean;
  scopeType: string;
  scopeValue: string | null;
  market: string;
  description: string | null;
  lastStatus: string | null;
  lastError: string | null;
  lastFetchedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

const fixtureIntelligenceSources: IntelligenceSourceFixture[] = [
  {
    id: 701,
    name: 'Market fixture feed',
    sourceType: 'rss',
    url: 'https://example.invalid/market-feed.xml',
    enabled: true,
    scopeType: 'market',
    scopeValue: null,
    market: 'cn',
    description: 'Deterministic playground intelligence source.',
    lastStatus: 'success',
    lastError: null,
    lastFetchedAt: FIXTURE_TIMESTAMP,
    createdAt: FIXTURE_TIMESTAMP,
    updatedAt: FIXTURE_TIMESTAMP,
  },
];

const fixtureIntelligenceTemplates = [
  {
    templateId: 'fixture-market-feed',
    name: 'Fixture market feed',
    sourceType: 'rss',
    url: 'https://example.invalid/template-feed.xml',
    scopeType: 'market',
    scopeValue: null,
    market: 'cn',
    description: 'Local template for component interaction previews.',
  },
];

const fixtureIntelligenceItems = [
  {
    id: 801,
    sourceId: 701,
    sourceName: 'Market fixture feed',
    sourceType: 'rss',
    title: 'Fixture intelligence item',
    summary: 'A deterministic research item rendered without external traffic.',
    url: 'https://example.invalid/intelligence/801',
    source: 'playground',
    publishedAt: FIXTURE_TIMESTAMP,
    fetchedAt: FIXTURE_TIMESTAMP,
    scopeType: 'market',
    scopeValue: null,
    market: 'cn',
  },
];

const fixtureBackendStatus = {
  backendId: 'fixture-backend',
  backendType: 'litellm',
  providerId: 'fixture-cloud',
  available: true,
  healthStatus: 'passed',
  supportsJson: true,
  supportsTools: true,
  supportsStream: true,
  supportsVision: false,
  isPrimary: true,
  fallbackTarget: null,
  maxConcurrency: 4,
  usageAvailable: true,
  lastErrorCode: null,
  lastErrorMessage: null,
};

const errorPayload = {
  error: 'playground_fixture_error',
  message: 'The selected playground profile returns a deterministic service error.',
  details: { source: 'component_playground' },
};

function responseFor<T>(profile: PlaygroundFixtureProfile, ready: T, empty: T): [number, T | typeof errorPayload] {
  if (profile === 'error') return [503, errorPayload];
  return [200, profile === 'empty' ? empty : ready];
}

function requestPath(config: InternalAxiosRequestConfig): string {
  const raw = config.url || '/api';
  try {
    return new URL(raw, window.location.origin).pathname;
  } catch {
    return raw.split('?')[0] || '/api';
  }
}

function postFrameMessage(message: unknown) {
  if (window.parent === window) return;
  window.parent.postMessage(message, window.location.origin);
}

function readJsonRecord(value: unknown): Record<string, unknown> {
  if (typeof value !== 'string') return {};
  try {
    const parsed = JSON.parse(value) as unknown;
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {};
  } catch {
    return {};
  }
}

export function installPlaygroundApiMock(
  profile: PlaygroundFixtureProfile,
  options: InstallPlaygroundApiMockOptions = {},
) {
  const state: MockState = {
    configVersion: 1,
    configItems: fixtureSystemConfigItems.map((item) => ({
      ...item,
      schema: item.schema ? { ...item.schema } : undefined,
    })),
    watchlist: ['600519', 'AAPL'],
    alertRules: fixtureAlertRules.map((item) => ({ ...item })),
    decisionSignals: [{ ...fixtureDecisionSignal }],
    intelligenceSources: profile === 'empty'
      ? []
      : fixtureIntelligenceSources.map((item) => ({ ...item })),
    authStatus: {
      authEnabled: false,
      loggedIn: true,
      passwordSet: true,
      passwordChangeable: true,
      setupState: 'password_retained',
    },
  };
  const delayResponse = options.delayResponse ?? (profile === 'slow' ? 1200 : 120);
  const mock = new AxiosMockAdapter(apiClient, { delayResponse });
  let requestSequence = 0;

  const requestInterceptor = apiClient.interceptors.request.use((config) => {
    const timed = config as TimedRequestConfig;
    requestSequence += 1;
    timed.__playgroundRequestId = `playground-request-${requestSequence}`;
    timed.__playgroundStartedAt = performance.now();
    return config;
  });

  const emitLog = (config: TimedRequestConfig | undefined, status: number) => {
    if (!config) return;
    const event: PlaygroundRequestLog = {
      id: config.__playgroundRequestId ?? `playground-request-${requestSequence}`,
      method: (config.method || 'get').toUpperCase(),
      path: requestPath(config),
      status,
      durationMs: Math.max(0, Math.round(performance.now() - (config.__playgroundStartedAt ?? performance.now()))),
    };
    options.onRequestLog?.(event);
    postFrameMessage({
      channel: 'stockpulse-playground',
      version: 1,
      type: 'api-log',
      event,
    });
  };

  const responseInterceptor = apiClient.interceptors.response.use(
    (response) => {
      emitLog(response.config as TimedRequestConfig, response.status);
      return response;
    },
    (error: AxiosError) => {
      emitLog(error.config as TimedRequestConfig | undefined, error.response?.status ?? 0);
      return Promise.reject(error);
    },
  );

  mock.onGet('/api/v1/portfolio/accounts').reply(() => responseFor(profile, {
    accounts: [
      { id: 1, name: 'Primary fixture account', market: 'cn', baseCurrency: 'CNY', isActive: true },
      { id: 2, name: 'US fixture account', market: 'us', baseCurrency: 'USD', isActive: true },
    ],
  }, { accounts: [] }));

  mock.onGet('/api/v1/history').reply(() => responseFor(profile, {
    total: fixtureHistoryItems.length,
    page: 1,
    limit: 20,
    items: fixtureHistoryItems,
  }, { total: 0, page: 1, limit: 20, items: [] }));
  mock.onGet('/api/v1/history/stocks').reply(() => responseFor(profile, {
    total: fixtureStockBarItems.length,
    items: fixtureStockBarItems,
  }, { total: 0, items: [] }));
  mock.onGet(/\/api\/v1\/history\/\d+\/news$/).reply(() => responseFor(profile, {
    total: 2,
    items: [
      { title: 'Earnings visibility improves', snippet: 'Fixture news summary for deterministic component rendering.', url: 'https://example.invalid/news/1' },
      { title: 'Sector breadth expands', snippet: 'A second fixture item exercises list spacing and wrapping.', url: 'https://example.invalid/news/2' },
    ],
  }, { total: 0, items: [] }));
  mock.onGet(/\/api\/v1\/history\/\d+\/markdown$/).reply(() => responseFor(profile, {
    content: '# Fixture report\n\n## Summary\n\nTrend remains constructive.\n\n- Support: 1450\n- Risk: valuation\n',
  }, { content: '' }));
  mock.onGet(/\/api\/v1\/history\/\d+\/diagnostics$/).reply(() => responseFor(profile, fixtureDiagnosticSummary, {
    ...fixtureDiagnosticSummary,
    status: 'unknown',
    statusLabel: 'Unknown',
    reason: '',
    components: {},
    copyText: '',
  }));
  mock.onGet(/\/api\/v1\/history\/\d+\/flow$/).reply(() => responseFor(profile, fixtureRunFlowSnapshot, {
    ...fixtureRunFlowSnapshot,
    status: 'unknown',
    nodes: [],
    edges: [],
    events: [],
    summary: { ...fixtureRunFlowSnapshot.summary, failedAttempts: 0, fallbackCount: 0, dataSourceCount: 0, eventCount: 0 },
  }));
  mock.onGet(/\/api\/v1\/history\/\d+$/).reply(() => responseFor(profile, fixtureReport, fixtureReport));
  mock.onGet(/\/api\/v1\/analysis\/tasks\/[^/]+\/flow$/).reply(() => responseFor(profile, fixtureRunFlowSnapshot, {
    ...fixtureRunFlowSnapshot,
    status: 'pending',
    nodes: [],
    edges: [],
    events: [],
  }));

  mock.onGet('/api/v1/system/config').reply(() => responseFor(profile, {
    configVersion: `fixture-v${state.configVersion}`,
    maskToken: '******',
    items: state.configItems,
    configuredNotificationChannels: ['email', 'custom'],
    updatedAt: FIXTURE_TIMESTAMP,
  }, {
    configVersion: `fixture-v${state.configVersion}`,
    maskToken: '******',
    items: [],
    configuredNotificationChannels: [],
    updatedAt: FIXTURE_TIMESTAMP,
  }));
  mock.onGet('/api/v1/system/config/schema').reply(() => responseFor(profile, {
    schemaVersion: 'fixture-v1',
    categories: [],
  }, { schemaVersion: 'fixture-v1', categories: [] }));
  mock.onGet('/api/v1/system/config/setup/status').reply(() => responseFor(profile, {
    isComplete: true,
    readyForSmoke: true,
    requiredMissingKeys: [],
    checks: [],
  }, {
    isComplete: false,
    readyForSmoke: false,
    requiredMissingKeys: [],
    checks: [],
  }));
  mock.onGet('/api/v1/system/config/llm/providers').reply(() => responseFor(profile, {
    providers: fixtureProviders,
    connectionFields: fixtureConnectionFields,
    emptyApiKeyHosts: [],
  }, { providers: [], connectionFields: [], emptyApiKeyHosts: [] }));
  mock.onGet('/api/v1/system/config/llm/available-models').reply(() => responseFor(profile, {
    models: [
      {
        modelRef: 'modelref:v1:fixture:fixture-route',
        route: 'fixture/fixture-route',
        display: 'Fixture Route',
        connection: 'fixture',
        connectionId: 'fixture',
        connectionName: 'Fixture connection',
        provider: 'openai',
        providerId: 'fixture-cloud',
        providerLabel: 'Fixture Cloud',
        available: true,
      },
    ],
  }, { models: [] }));
  mock.onGet('/api/v1/system/config/llm/mode-status').reply(() => responseFor(profile, {
    requestedMode: 'auto',
    effectiveMode: 'legacy',
    detectedSources: ['legacy'],
    overriddenSources: [],
    issues: [],
  }, {
    requestedMode: 'auto',
    effectiveMode: null,
    detectedSources: [],
    overriddenSources: [],
    issues: [],
  }));
  mock.onGet('/api/v1/system/config/llm/legacy-migration/preview').reply(() => responseFor(profile, {
    channels: [{ name: 'fixture', protocol: 'openai', baseUrl: 'https://api.example.invalid/v1', model: 'fixture-route' }],
  }, { channels: [] }));
  mock.onPost('/api/v1/system/config/llm/legacy-migration/apply').reply(() => {
    if (profile === 'error') return [503, errorPayload];
    state.configVersion += 1;
    return [200, {
      success: true,
      configVersion: `fixture-v${state.configVersion}`,
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: false,
      updatedKeys: ['LLM_CHANNELS'],
      warnings: [],
    }];
  });

  const backendStatusResponse = {
    primaryBackendId: fixtureBackendStatus.backendId,
    fallbackBackendId: null,
    primary: fixtureBackendStatus,
    fallback: null,
    backends: [fixtureBackendStatus],
  };
  mock.onGet('/api/v1/system/config/generation-backends/status').reply(() => responseFor(profile, backendStatusResponse, {
    ...backendStatusResponse,
    primary: { ...fixtureBackendStatus, available: false, healthStatus: 'not_tested' },
    backends: [],
  }));
  mock.onPost('/api/v1/system/config/generation-backends/status/preview').reply(() => responseFor(profile, backendStatusResponse, {
    ...backendStatusResponse,
    primary: { ...fixtureBackendStatus, available: false, healthStatus: 'not_tested' },
    backends: [],
  }));
  mock.onPost('/api/v1/system/config/generation-backends/smoke-test').reply(() => responseFor(profile, {
    success: true,
    mode: 'json',
    message: 'Fixture smoke test passed.',
    status: fixtureBackendStatus,
  }, {
    success: false,
    mode: 'json',
    message: 'No fixture backend is configured.',
    status: { ...fixtureBackendStatus, available: false, healthStatus: 'skipped' },
  }));
  mock.onPost('/api/v1/system/config/llm/test-channel').reply(() => responseFor(profile, {
    success: true,
    message: 'Fixture connection succeeded.',
    resolvedProtocol: 'openai',
    resolvedModel: 'fixture-route',
    latencyMs: 42,
    capabilityResults: {},
  }, {
    success: false,
    message: 'No fixture model selected.',
    errorCode: 'empty_fixture',
    retryable: false,
    capabilityResults: {},
  }));
  mock.onPost('/api/v1/system/config/llm/discover-models').reply(() => responseFor(profile, {
    success: true,
    message: 'Fixture models discovered.',
    resolvedProtocol: 'openai',
    models: ['fixture-route', 'fixture-route-fast'],
    latencyMs: 38,
  }, {
    success: true,
    message: 'No fixture models found.',
    resolvedProtocol: 'openai',
    models: [],
    latencyMs: 38,
  }));
  mock.onPost('/api/v1/system/config/notification/test-channel').reply(() => responseFor(profile, {
    success: true,
    message: 'Fixture notification delivered.',
    retryable: false,
    latencyMs: 32,
    attempts: [{ channel: 'email', success: true, message: 'Delivered', stage: 'dispatch', retryable: false, latencyMs: 32, httpStatus: 200 }],
  }, {
    success: false,
    message: 'No fixture channel configured.',
    errorCode: 'empty_fixture',
    stage: 'validation',
    retryable: false,
    attempts: [],
  }));
  mock.onPost('/api/v1/system/config/validate').reply(() => responseFor(profile, { valid: true, issues: [] }, { valid: true, issues: [] }));
  mock.onPut('/api/v1/system/config').reply((config) => {
    if (profile === 'error') return [503, errorPayload];
    const body = readJsonRecord(config.data);
    const updates = Array.isArray(body.items) ? body.items : [];
    const nextValues = new Map(updates.flatMap((item) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) return [];
      const record = item as Record<string, unknown>;
      return typeof record.key === 'string' && typeof record.value === 'string'
        ? [[record.key, record.value] as const]
        : [];
    }));
    state.configItems = state.configItems.map((item) => nextValues.has(item.key)
      ? { ...item, value: nextValues.get(item.key) ?? '', rawValueExists: true }
      : item);
    state.configVersion += 1;
    return [200, {
      success: true,
      configVersion: `fixture-v${state.configVersion}`,
      appliedCount: nextValues.size,
      skippedMaskedCount: 0,
      reloadTriggered: false,
      updatedKeys: [...nextValues.keys()],
      warnings: [],
    }];
  });

  mock.onPost('/api/v1/stocks/extract-from-image').reply(() => responseFor(profile, {
    codes: ['600519', 'AAPL'],
    items: [
      { code: '600519', name: 'Kweichow Moutai', confidence: 'high' },
      { code: 'AAPL', name: 'Apple', confidence: 'medium' },
    ],
    raw_text: '600519 AAPL',
  }, { codes: [], items: [], raw_text: '' }));
  mock.onPost('/api/v1/stocks/parse-import').reply(() => responseFor(profile, {
    codes: ['600519', 'AAPL'],
    items: [
      { code: '600519', name: 'Kweichow Moutai', confidence: 'high' },
      { code: 'AAPL', name: 'Apple', confidence: 'high' },
    ],
  }, { codes: [], items: [] }));

  mock.onGet('/api/v1/stocks/watchlist').reply(() => responseFor(profile, { stockCodes: state.watchlist }, { stockCodes: [] }));
  mock.onPost('/api/v1/stocks/watchlist/add').reply((config) => {
    if (profile === 'error') return [503, errorPayload];
    const body = typeof config.data === 'string' ? JSON.parse(config.data) as { stock_code?: string } : {};
    if (body.stock_code && !state.watchlist.includes(body.stock_code)) state.watchlist.push(body.stock_code);
    return [200, { stockCodes: state.watchlist }];
  });
  mock.onPost('/api/v1/stocks/watchlist/remove').reply((config) => {
    if (profile === 'error') return [503, errorPayload];
    const body = typeof config.data === 'string' ? JSON.parse(config.data) as { stock_code?: string } : {};
    state.watchlist = state.watchlist.filter((item) => item !== body.stock_code);
    return [200, { stockCodes: state.watchlist }];
  });

  mock.onGet('/api/v1/auth/status').reply(() => responseFor(profile, state.authStatus, {
    authEnabled: false,
    loggedIn: true,
    passwordSet: false,
    passwordChangeable: false,
    setupState: 'no_password',
  }));
  mock.onPost('/api/v1/auth/settings').reply((config) => {
    if (profile === 'error') return [503, errorPayload];
    const body = readJsonRecord(config.data);
    const authEnabled = body.authEnabled === true;
    state.authStatus = {
      ...state.authStatus,
      authEnabled,
      passwordSet: state.authStatus.passwordSet || typeof body.password === 'string',
      passwordChangeable: true,
      setupState: authEnabled ? 'enabled' : 'password_retained',
    };
    return [200, state.authStatus];
  });
  mock.onPost('/api/v1/auth/change-password').reply(() => profile === 'error' ? [503, errorPayload] : [204]);

  mock.onPost('/api/v1/agent/research').reply(() => responseFor(profile, {
    success: true,
    content: 'Fixture research found improving breadth with valuation risk still elevated.',
    sources: ['How durable is the earnings trend?', 'Which risks could invalidate the thesis?'],
    token_usage: 128,
  }, {
    success: true,
    content: '',
    sources: [],
    token_usage: 0,
  }));

  mock.onPost('/api/v1/decision-signals/outcomes/run').reply(() => responseFor(profile, {
    items: [fixtureDecisionOutcome],
    evaluated: 25,
    created: 15,
    updated: 10,
    skipped: 65,
    engine_version: 'playground-v1',
  }, {
    items: [],
    evaluated: 0,
    created: 0,
    updated: 0,
    skipped: 0,
    engine_version: 'playground-v1',
  }));
  mock.onGet('/api/v1/decision-signals').reply(() => {
    if (profile === 'error') return [503, errorPayload];
    return [200, {
      items: state.decisionSignals,
      total: state.decisionSignals.length,
      page: 1,
      page_size: 20,
    }];
  });
  mock.onPost('/api/v1/decision-signals').reply((config) => {
    if (profile === 'error') return [503, errorPayload];
    const body = readJsonRecord(config.data);
    const created = {
      ...fixtureDecisionSignal,
      id: Math.max(0, ...state.decisionSignals.map((item) => item.id)) + 1,
      stockCode: typeof body.stock_code === 'string' ? body.stock_code : fixtureDecisionSignal.stockCode,
      stockName: typeof body.stock_name === 'string' ? body.stock_name : null,
      market: typeof body.market === 'string' ? body.market : fixtureDecisionSignal.market,
      sourceType: 'manual',
      triggerSource: 'web_manual',
      action: typeof body.action === 'string' ? body.action : fixtureDecisionSignal.action,
      traceId: typeof body.trace_id === 'string' ? body.trace_id : `playground-manual-${state.decisionSignals.length + 1}`,
      createdAt: FIXTURE_TIMESTAMP,
      updatedAt: FIXTURE_TIMESTAMP,
    } as typeof fixtureDecisionSignal;
    state.decisionSignals.push(created);
    return [200, { item: created, created: true }];
  });

  mock.onGet('/api/v1/intelligence/sources/templates').reply(() => responseFor(profile, {
    items: fixtureIntelligenceTemplates,
    total: fixtureIntelligenceTemplates.length,
  }, { items: [], total: 0 }));
  mock.onPost('/api/v1/intelligence/sources/defaults').reply(() => {
    if (profile === 'error') return [503, errorPayload];
    const createdItems = fixtureIntelligenceSources.flatMap((source) => {
      if (state.intelligenceSources.some((item) => item.url === source.url)) return [];
      const created = { ...source, id: Math.max(700, ...state.intelligenceSources.map((item) => item.id)) + 1 };
      state.intelligenceSources.push(created);
      return [{ created: true, source: created }];
    });
    return [200, { items: createdItems, created_count: createdItems.length, total: state.intelligenceSources.length }];
  });
  mock.onPost('/api/v1/intelligence/sources/test').reply(() => responseFor(profile, {
    ok: true,
    source: { source_type: 'rss', market: 'cn' },
    fetched_count: 1,
    sample_items: fixtureIntelligenceItems,
  }, { ok: true, source: {}, fetched_count: 0, sample_items: [] }));
  mock.onPost('/api/v1/intelligence/sources/fetch-enabled').reply(() => responseFor(profile, {
    ok: true,
    source_count: state.intelligenceSources.length,
    fetched_count: fixtureIntelligenceItems.length,
    saved_count: fixtureIntelligenceItems.length,
    sample_items: fixtureIntelligenceItems,
  }, { ok: true, source_count: 0, fetched_count: 0, saved_count: 0, sample_items: [] }));
  mock.onPost(/\/api\/v1\/intelligence\/sources\/templates\/[^/]+$/).reply(() => {
    if (profile === 'error') return [503, errorPayload];
    const template = fixtureIntelligenceTemplates[0];
    const created: IntelligenceSourceFixture = {
      ...fixtureIntelligenceSources[0],
      id: Math.max(700, ...state.intelligenceSources.map((item) => item.id)) + 1,
      name: template.name,
      url: template.url,
    };
    state.intelligenceSources.push(created);
    return [200, created];
  });
  mock.onPost(/\/api\/v1\/intelligence\/sources\/\d+\/fetch$/).reply((config) => {
    if (profile === 'error') return [503, errorPayload];
    const sourceId = Number(requestPath(config as InternalAxiosRequestConfig).split('/').at(-2));
    return [200, {
      ok: true,
      source_id: sourceId,
      fetched_count: fixtureIntelligenceItems.length,
      saved_count: fixtureIntelligenceItems.length,
      dry_run: config.params?.dry_run === true,
      sample_items: fixtureIntelligenceItems,
    }];
  });
  mock.onGet('/api/v1/intelligence/sources').reply(() => {
    if (profile === 'error') return [503, errorPayload];
    return [200, {
      items: state.intelligenceSources,
      total: state.intelligenceSources.length,
      page: 1,
      page_size: 100,
    }];
  });
  mock.onPost('/api/v1/intelligence/sources').reply((config) => {
    if (profile === 'error') return [503, errorPayload];
    const body = readJsonRecord(config.data);
    const created: IntelligenceSourceFixture = {
      ...fixtureIntelligenceSources[0],
      id: Math.max(700, ...state.intelligenceSources.map((item) => item.id)) + 1,
      name: typeof body.name === 'string' ? body.name : 'Fixture source',
      url: typeof body.url === 'string' ? body.url : 'https://example.invalid/source.xml',
      sourceType: typeof body.source_type === 'string' ? body.source_type : 'rss',
      scopeType: typeof body.scope_type === 'string' ? body.scope_type : 'market',
      scopeValue: typeof body.scope_value === 'string' ? body.scope_value : null,
      market: typeof body.market === 'string' ? body.market : 'cn',
      description: typeof body.description === 'string' ? body.description : null,
      enabled: body.enabled !== false,
    };
    state.intelligenceSources.push(created);
    return [200, created];
  });
  mock.onGet('/api/v1/intelligence/items').reply(() => responseFor(profile, {
    items: fixtureIntelligenceItems,
    total: fixtureIntelligenceItems.length,
    page: 1,
    page_size: 20,
  }, { items: [], total: 0, page: 1, page_size: 20 }));

  mock.onGet('/api/v1/alerts/rules').reply(() => responseFor(profile, {
    items: state.alertRules,
    total: state.alertRules.length,
    page: 1,
    pageSize: 20,
  }, { items: [], total: 0, page: 1, pageSize: 20 }));
  mock.onPost('/api/v1/alerts/rules').reply((config) => {
    if (profile === 'error') return [503, errorPayload];
    const body = readJsonRecord(config.data);
    const created = {
      ...fixtureAlertRules[0],
      name: typeof body.name === 'string' ? body.name : fixtureAlertRules[0].name,
      targetScope: typeof body.target_scope === 'string' ? body.target_scope : fixtureAlertRules[0].targetScope,
      target: typeof body.target === 'string' ? body.target : fixtureAlertRules[0].target,
      alertType: typeof body.alert_type === 'string' ? body.alert_type : fixtureAlertRules[0].alertType,
      parameters: body.parameters && typeof body.parameters === 'object' ? body.parameters : fixtureAlertRules[0].parameters,
      severity: typeof body.severity === 'string' ? body.severity : fixtureAlertRules[0].severity,
      enabled: typeof body.enabled === 'boolean' ? body.enabled : true,
      id: Math.max(0, ...state.alertRules.map((item) => item.id)) + 1,
      source: 'playground',
    } as typeof fixtureAlertRules[number];
    state.alertRules.push(created);
    return [200, created];
  });
  mock.onDelete(/\/api\/v1\/alerts\/rules\/\d+$/).reply((config) => {
    if (profile === 'error') return [503, errorPayload];
    const id = Number(requestPath(config as InternalAxiosRequestConfig).split('/').at(-1));
    const before = state.alertRules.length;
    state.alertRules = state.alertRules.filter((item) => item.id !== id);
    return [200, { deleted: before - state.alertRules.length }];
  });
  mock.onPost(/\/api\/v1\/alerts\/rules\/\d+\/(enable|disable)$/).reply((config) => {
    if (profile === 'error') return [503, errorPayload];
    const parts = requestPath(config as InternalAxiosRequestConfig).split('/');
    const id = Number(parts.at(-2));
    const enabled = parts.at(-1) === 'enable';
    const index = state.alertRules.findIndex((item) => item.id === id);
    if (index < 0) return [404, { error: 'not_found', message: 'playground_fixture_error' }];
    state.alertRules[index] = { ...state.alertRules[index], enabled };
    return [200, state.alertRules[index]];
  });
  mock.onPost(/\/api\/v1\/alerts\/rules\/\d+\/test$/).reply((config) => {
    if (profile === 'error') return [503, errorPayload];
    const id = Number(requestPath(config as InternalAxiosRequestConfig).split('/').at(-2));
    return [200, {
      ruleId: id,
      status: 'triggered',
      triggered: true,
      observedValue: 1502.2,
      message: 'playground_fixture_triggered',
    }];
  });
  mock.onGet('/api/v1/alerts/triggers').reply(() => responseFor(profile, {
    items: fixtureAlertTriggers,
    total: fixtureAlertTriggers.length,
    page: 1,
    pageSize: 20,
  }, { items: [], total: 0, page: 1, pageSize: 20 }));

  mock.onAny().reply((config) => [501, {
    error: 'playground_mock_not_registered',
    message: `No playground mock is registered for ${(config.method || 'get').toUpperCase()} ${requestPath(config as InternalAxiosRequestConfig)}.`,
  }]);

  return {
    mock,
    restore() {
      apiClient.interceptors.request.eject(requestInterceptor);
      apiClient.interceptors.response.eject(responseInterceptor);
      mock.restore();
    },
  };
}
