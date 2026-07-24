// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { writeFile } from 'node:fs/promises';
import { createHash, randomBytes } from 'node:crypto';
import {
  expect,
  test,
  type Locator,
  type Page,
  type Route,
} from '@playwright/test';
import { encodeModelRef } from '../src/utils/modelRef';
import { BACKTEST_TEXT } from '../src/locales/backtest';
import { PORTFOLIO_TEXT } from '../src/locales/portfolio';
import { SCREENING_TEXT } from '../src/locales/screening';
import { UI_TEXT } from '../src/i18n/uiText';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  LEGACY_ALERTS_VIEW_VALUES,
  LEGACY_ROUTE_PATHS,
  RESEARCH_DISCOVER_DEFAULT_VALUES,
  RESEARCH_DISCOVER_ROUTE_QUERY_KEYS,
  SIGNAL_CENTER_HISTORY_VALUES,
  SIGNAL_CENTER_ROUTE_QUERY_KEYS,
  SIGNAL_CENTER_SCOPE_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
  SIGNAL_FEED_ROUTE_QUERY_KEYS,
  SIGNAL_FEED_VIEW_VALUES,
  SETTINGS_ROUTE_QUERY_KEYS,
  SETTINGS_SECTION_IDS,
  buildAnalysisWorkbenchHref,
  buildSignalCenterHref,
  buildSettingsHref,
  buildSettingsSectionHref,
} from '../src/routing/routes';
import { loginAsE2eAdmin, mockCompletedSetupStatus, updateE2eConfigOutsidePlaywrightTrace } from './auth-fixture';

type JsonObject = Record<string, unknown>;

const fakeProviderPort = Number(process.env.DSA_WEB_SMOKE_PROVIDER_PORT || 18101);
const fakeProviderOrigin = `http://127.0.0.1:${fakeProviderPort}`;
const fakeProviderBaseUrl = `http://127.0.0.1:${fakeProviderPort}/v1`;
const uiLanguageStorageKey = 'dsa.uiLanguage';
const screeningTaskStorageKey = 'dsa.alphasift.activeScreenTask.v1';
const usageSettingsHref = buildSettingsSectionHref(SETTINGS_SECTION_IDS.usage);
const settingsHrefs = {
  modelConnections: buildSettingsHref({ section: 'ai_models', view: 'connections' }),
  modelTaskRouting: buildSettingsHref({ section: 'ai_models', view: 'task_routing' }),
  modelReliability: buildSettingsHref({ section: 'ai_models', view: 'reliability' }),
  advancedDiagnostics: buildSettingsHref({ section: 'advanced', view: 'diagnostics' }),
  systemService: buildSettingsHref({ section: 'system_security', view: 'service' }),
} as const;

const MODEL_KEYS_TO_RESET = [
  'LLM_CONFIG_MODE',
  'LLM_CHANNELS',
  'LLM_E2E_PROTOCOL',
  'LLM_E2E_PROVIDER',
  'LLM_E2E_BASE_URL',
  'LLM_E2E_API_KEY',
  'LLM_E2E_API_KEYS',
  'LLM_E2E_MODELS',
  'LLM_E2E_ENABLED',
  'LLM_OPENAI_DISPLAY_NAME',
  'LLM_OPENAI_PROTOCOL',
  'LLM_OPENAI_PROVIDER',
  'LLM_OPENAI_BASE_URL',
  'LLM_OPENAI_API_KEY',
  'LLM_OPENAI_API_KEYS',
  'LLM_OPENAI_MODELS',
  'LLM_OPENAI_ENABLED',
  'LLM_ALPHA_CONN_DISPLAY_NAME',
  'LLM_ALPHA_CONN_PROTOCOL',
  'LLM_ALPHA_CONN_PROVIDER',
  'LLM_ALPHA_CONN_BASE_URL',
  'LLM_ALPHA_CONN_API_KEY',
  'LLM_ALPHA_CONN_API_KEYS',
  'LLM_ALPHA_CONN_MODELS',
  'LLM_ALPHA_CONN_ENABLED',
  'LLM_BETA_CONN_PROTOCOL',
  'LLM_BETA_CONN_PROVIDER',
  'LLM_BETA_CONN_BASE_URL',
  'LLM_BETA_CONN_API_KEY',
  'LLM_BETA_CONN_API_KEYS',
  'LLM_BETA_CONN_MODELS',
  'LLM_BETA_CONN_ENABLED',
  'LLM_BETA_CONN_DISPLAY_NAME',
  'LLM_PRIMARY_GATEWAY_PROTOCOL',
  'LLM_PRIMARY_GATEWAY_PROVIDER',
  'LLM_PRIMARY_GATEWAY_BASE_URL',
  'LLM_PRIMARY_GATEWAY_API_KEY',
  'LLM_PRIMARY_GATEWAY_API_KEYS',
  'LLM_PRIMARY_GATEWAY_MODELS',
  'LLM_PRIMARY_GATEWAY_ENABLED',
  'LITELLM_MODEL',
  'AGENT_LITELLM_MODEL',
  'VISION_MODEL',
  'LITELLM_FALLBACK_MODELS',
];

function deferred<T = void>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

async function getElementContrast(locator: Locator) {
  return locator.evaluate((node) => {
    const toRgba = (color: string): [number, number, number, number] => {
      const canvas = document.createElement('canvas');
      canvas.width = 1;
      canvas.height = 1;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      if (!context) throw new Error('Canvas 2D context unavailable');
      context.clearRect(0, 0, 1, 1);
      context.fillStyle = color;
      context.fillRect(0, 0, 1, 1);
      const [red, green, blue, alpha] = context.getImageData(0, 0, 1, 1).data;
      return [red, green, blue, alpha / 255];
    };
    const luminance = (rgb: [number, number, number]) => {
      const channels = rgb.map((channel) => {
        const normalized = channel / 255;
        return normalized <= 0.04045
          ? normalized / 12.92
          : ((normalized + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    };
    const foreground = getComputedStyle(node).color;
    const foregroundRgba = toRgba(foreground);
    let backgroundNode: Element | null = node;
    let background = 'rgba(0, 0, 0, 0)';
    let backgroundRgba = toRgba(background);
    let effectiveOpacity = 1;
    while (backgroundNode) {
      const style = getComputedStyle(backgroundNode);
      effectiveOpacity *= Number(style.opacity || '1');
      const candidate = style.backgroundColor;
      const candidateRgba = toRgba(candidate);
      if (candidateRgba[3] > 0) {
        background = candidate;
        backgroundRgba = candidateRgba;
        break;
      }
      backgroundNode = backgroundNode.parentElement;
    }
    const backgroundRgb = backgroundRgba.slice(0, 3) as [number, number, number];
    const foregroundAlpha = foregroundRgba[3] * effectiveOpacity;
    const compositedForeground = foregroundRgba.slice(0, 3).map((channel, index) => (
      channel * foregroundAlpha + backgroundRgb[index] * (1 - foregroundAlpha)
    )) as [number, number, number];
    const foregroundLuminance = luminance(compositedForeground);
    const backgroundLuminance = luminance(backgroundRgb);
    const ratio = (Math.max(foregroundLuminance, backgroundLuminance) + 0.05)
      / (Math.min(foregroundLuminance, backgroundLuminance) + 0.05);
    return { foreground, background, effectiveOpacity, ratio };
  });
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function expectMinimumTouchTarget(locator: Locator, minimum = 44) {
  await expect(locator).toBeVisible();
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.width).toBeGreaterThanOrEqual(minimum);
  expect(box!.height).toBeGreaterThanOrEqual(minimum);
}

async function login(page: Page, language: 'zh' | 'en' = 'zh') {
  await mockCompletedSetupStatus(page);
  await loginAsE2eAdmin(page);
  if (language === 'en') {
    await page.evaluate((key) => localStorage.setItem(key, 'en'), uiLanguageStorageKey);
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  } else {
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  }
}

async function selectUiLanguage(page: Page, language: 'zh' | 'en') {
  await page.getByRole('button', { name: 'StockPulse', exact: true }).last().click();
  const selector = page.locator('[data-testid="ui-language-selector"]:visible [role="combobox"]').first();
  await selector.click();
  await page.locator(`[role="option"][data-value="${language}"]`).click();
}

async function selectTheme(page: Page, optionName: '浅色' | '深色') {
  const toggle = page.getByRole('button', { name: '切换主题' }).first();
  if (!await toggle.isVisible().catch(() => false)) {
    await page.getByRole('button', { name: 'StockPulse', exact: true }).last().click();
  }
  await toggle.click();
  await page.getByRole('menuitemradio', { name: optionName, exact: true }).click();
}

async function installMockAuth(page: Page, options: {
  language: 'zh' | 'en';
  passwordSet: boolean;
  loginStatus?: number;
  loginError?: JsonObject;
}) {
  let loggedIn = false;
  let submitted: JsonObject | null = null;
  await page.addInitScript(({ key, language }) => {
    localStorage.setItem(key, language);
  }, { key: uiLanguageStorageKey, language: options.language });
  // The mock-auth world must keep every /api/v1 response authorized. After a
  // mocked login the app has no real session, so workspace requests reaching
  // the real backend return 401 and the global unauthorized interceptor
  // hard-redirects back to /login, looping forever between / and /login.
  // Playwright matches routes in reverse registration order, so the auth
  // routes registered below take precedence over this catch-all.
  await page.route('**/api/v1/**', async (route) => {
    await fulfillJson(route, {});
  });
  await page.route('**/api/v1/auth/status', async (route) => {
    await fulfillJson(route, {
      authEnabled: true,
      loggedIn,
      passwordSet: options.passwordSet,
      passwordChangeable: true,
      setupState: options.passwordSet ? 'enabled' : 'no_password',
    });
  });
  await page.route('**/api/v1/auth/login', async (route) => {
    submitted = route.request().postDataJSON() as JsonObject;
    if ((options.loginStatus ?? 200) !== 200) {
      await fulfillJson(route, options.loginError ?? {
        error: 'invalid_credentials',
        message: 'diagnostic only',
        params: {},
      }, options.loginStatus ?? 401);
      return;
    }
    loggedIn = true;
    await fulfillJson(route, { success: true });
  });
  return {
    submitted: () => submitted,
    reset: () => {
      loggedIn = false;
      submitted = null;
    },
  };
}

async function openSeededReport(page: Page, uiLanguage: 'zh' | 'en', reportLanguage: 'zh' | 'en') {
  await page.route('**/api/v1/history/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (!/\/api\/v1\/history\/\d+$/.test(pathname)) {
      await route.continue();
      return;
    }
    const response = await route.fetch();
    const body = await response.json() as JsonObject;
    const meta = body.meta as JsonObject;
    body.meta = { ...meta, report_language: reportLanguage };
    const details = (body.details as JsonObject | undefined) ?? {};
    body.details = {
      ...details,
      raw_result: { fixture: 'raw-diagnostic-value' },
      context_snapshot: { fixture: 'context-snapshot-value' },
    };
    await route.fulfill({ response, json: body });
  });
  await page.route('**/api/v1/history/*/diagnostics', async (route) => {
    await fulfillJson(route, {
      trace_id: 'trace-infrastructure-acceptance',
      task_id: 'task-infrastructure-acceptance',
      query_id: 'query-infrastructure-acceptance',
      stock_code: 'AAPL',
      trigger_source: 'e2e',
      status: 'normal',
      status_label: 'raw status label',
      reason: 'raw diagnostic reason',
      components: {},
      copy_text: 'trace_id: trace-infrastructure-acceptance',
    });
  });
  await login(page, uiLanguage);
  await page.goto(buildAnalysisWorkbenchHref({
    segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
  }));
  const historyItem = page.locator('.home-history-item').filter({ hasText: 'E2E Fixture' }).first();
  await expect(historyItem).toBeVisible({ timeout: 15_000 });
  await historyItem.click();
  await expect(page.getByText('E2E Fixture', { exact: true }).first()).toBeVisible({ timeout: 15_000 });
}

async function currentConfig(page: Page) {
  const response = await page.request.get('/api/v1/system/config');
  expect(response.ok(), await response.text()).toBe(true);
  return response.json() as Promise<{
    config_version: string;
    mask_token: string;
    items: Array<{
      key: string;
      value: string;
      raw_value_exists: boolean;
      is_masked: boolean;
      schema?: { is_sensitive?: boolean };
    }>;
  }>;
}

async function putConfigItems(
  page: Page,
  items: Array<{ key: string; value: string }>,
  expectedStatus = 200,
) {
  const config = await currentConfig(page);
  const response = await page.request.put('/api/v1/system/config', {
    data: {
      config_version: config.config_version,
      mask_token: config.mask_token || '******',
      reload_now: true,
      items,
    },
  });
  expect(response.status(), await response.text()).toBe(expectedStatus);
  return response;
}

async function resetModelConfig(page: Page) {
  await putConfigItems(page, MODEL_KEYS_TO_RESET.map((key) => ({
    key,
    value: key === 'LLM_CONFIG_MODE' ? 'auto' : '',
  })));
}

function connectionItems(id: string, model: string, provider = 'openai', apiKey = 'e2e-key') {
  const prefix = `LLM_${id.toUpperCase()}`;
  return [
    { key: `${prefix}_DISPLAY_NAME`, value: id },
    { key: `${prefix}_PROTOCOL`, value: 'openai' },
    { key: `${prefix}_PROVIDER`, value: provider },
    { key: `${prefix}_BASE_URL`, value: fakeProviderBaseUrl },
    { key: `${prefix}_API_KEY`, value: apiKey },
    { key: `${prefix}_MODELS`, value: model },
    { key: `${prefix}_ENABLED`, value: 'true' },
  ];
}

async function configureConnections(
  page: Page,
  definitions: Array<{ id: string; model: string; provider?: string; apiKey?: string }>,
  routes: Array<{ key: string; value: string }> = [],
) {
  await resetModelConfig(page);
  const items = [
    { key: 'LLM_CONFIG_MODE', value: 'auto' },
    { key: 'LLM_CHANNELS', value: definitions.map((entry) => entry.id).join(',') },
    ...definitions.flatMap((entry) => connectionItems(
      entry.id,
      entry.model,
      entry.provider,
      entry.apiKey,
    )),
    ...routes,
  ];
  await updateE2eConfigOutsidePlaywrightTrace(items);
}

function authorizationFingerprint(apiKey: string) {
  return createHash('sha256').update(`Bearer ${apiKey}`).digest('hex');
}

async function clearFakeProviderRequests(page: Page) {
  const response = await page.request.delete(`${fakeProviderOrigin}/__requests`);
  expect(response.ok(), await response.text()).toBe(true);
}

async function getFakeProviderRequests(page: Page) {
  const response = await page.request.get(`${fakeProviderOrigin}/__requests`);
  expect(response.ok(), await response.text()).toBe(true);
  return response.json() as Promise<{
    requests: Array<{
      method: string;
      path: string;
      authorization: boolean;
      authorization_sha256: string | null;
    }>;
  }>;
}

async function openConnections(page: Page, reset = true) {
  await login(page);
  if (reset) await resetModelConfig(page);
  await page.goto(settingsHrefs.modelConnections);
  await expect(page.getByRole('heading', { name: '模型接入' })).toBeVisible({ timeout: 15_000 });
}

async function addOpenAiConnectionThroughUi(page: Page, id: string, model: string) {
  await page.getByRole('button', { name: /添加模型服务/ }).first().click();
  const dialog = page.getByRole('dialog', { name: '添加模型服务' });
  await dialog.getByLabel('选择模型服务商').click();
  await page.locator('[role="option"][data-value="openai"]').click();
  await dialog.getByRole('button', { name: '下一步' }).click();
  await dialog.getByLabel('连接名称').fill(id);
  await dialog.getByLabel('API 密钥').fill('e2e-openai-key');
  await dialog.getByRole('button', { name: '使用自定义服务地址' }).click();
  await dialog.getByLabel('服务地址').fill(fakeProviderBaseUrl);
  const manualButton = dialog.getByRole('button', { name: /手动添加模型/ });
  if (await manualButton.isVisible().catch(() => false)) await manualButton.click();
  await dialog.getByLabel('手动添加模型').fill(model);
  await dialog.getByLabel('手动添加模型').press('Enter');
  const autosave = page.waitForResponse((response) => (
    response.url().endsWith('/api/v1/system/config')
    && response.request().method() === 'PUT'
  ));
  await dialog.getByRole('button', { name: '添加到配置' }).click();
  const response = await autosave;
  expect(response.status()).toBe(200);
  const payload = response.request().postDataJSON() as { items: Array<{ key: string; value: string }> };
  const channelIds = payload.items.find((item) => item.key === 'LLM_CHANNELS')?.value.split(',') ?? [];
  const addedConnectionId = channelIds.at(-1)?.trim();
  expect(addedConnectionId).toBeTruthy();
  await expect(page.getByText(/AI 模型: 已自动保存/)).toBeVisible();
  return addedConnectionId!;
}

async function editConnectionAddModel(page: Page, id: string, model: string) {
  await page.getByTestId(`connection-card-${id}`).getByRole('button', { name: '编辑' }).click();
  const dialog = page.getByRole('dialog', { name: '编辑模型服务' });
  const manualButton = dialog.getByRole('button', { name: /手动添加模型/ });
  if (await manualButton.isVisible().catch(() => false)) await manualButton.click();
  await dialog.getByLabel('手动添加模型').fill(model);
  await dialog.getByLabel('手动添加模型').press('Enter');
  await dialog.getByRole('button', { name: '保存修改' }).click();
  await expect(dialog).toBeHidden();
}

async function mockScreeningBase(page: Page, strategies: JsonObject[] = [{
  id: 'bull_trend',
  name: '中文原始策略名',
  name_zh: '多头趋势',
  name_en: 'Bull Trend',
  description: 'raw description',
  description_zh: '捕捉多头趋势',
  description_en: 'Capture established bullish trends',
  category_zh: '趋势',
  category_en: 'Trend',
}]) {
  await page.route('**/api/v1/alphasift/status', (route) => fulfillJson(route, {
    enabled: true,
    available: true,
    install_spec_is_default: true,
  }));
  await page.route('**/api/v1/alphasift/strategies', (route) => fulfillJson(route, {
    enabled: true,
    strategy_count: strategies.length,
    strategies,
  }));
  await page.route('**/api/v1/alphasift/hotspots**', (route) => fulfillJson(route, {
    hotspots: [],
    details: {},
    cached_at: null,
    diagnostics: {},
  }));
}

function screeningResult(marker: string) {
  return {
    run_id: `run-${marker}`,
    strategy: 'bull_trend',
    market: 'cn',
    snapshot_count: 1,
    filtered_count: 1,
    candidates: [{
      rank: 1,
      code: marker,
      name: `${marker} candidate`,
      score: 88,
      reason: `${marker} semantic result`,
      raw: {},
    }],
  };
}

function alertRule(id: number, name: string) {
  return {
    id,
    name,
    target_scope: 'single_symbol',
    target: id === 1 ? 'AAPL' : 'MSFT',
    alert_type: 'price_cross',
    parameters: { direction: 'above', price: 200 },
    severity: 'warning',
    enabled: true,
    source: 'e2e',
    created_at: '2026-07-15T12:00:00Z',
    updated_at: '2026-07-15T12:00:00Z',
  };
}

async function mockEmptyAlertCollections(page: Page, rules: unknown[] = []) {
  await page.route('**/api/v1/alerts/rules**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, { items: rules, total: rules.length, page: 1, page_size: 20 });
  });
  await page.route('**/api/v1/alerts/triggers**', (route) => fulfillJson(route, {
    items: [], total: 0, page: 1, page_size: 20,
  }));
  await page.route('**/api/v1/alerts/notifications**', (route) => fulfillJson(route, {
    items: [], total: 0, page: 1, page_size: 20,
  }));
}

async function mockSignalCenterCollections(page: Page, signals: unknown[] = []) {
  await mockEmptyAlertCollections(page);
  await page.route('**/api/v1/history/stocks**', (route) => fulfillJson(route, {
    items: [], total: 0,
  }));
  await page.route('**/api/v1/decision-signals**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/outcomes/stats')) {
      await fulfillJson(route, {
        engine_version: 'e2e',
        horizons: null,
        statuses: ['active', 'expired', 'invalidated', 'closed'],
        total: 0,
        completed: 0,
        unable: 0,
        hit: 0,
        miss: 0,
        neutral: 0,
        hit_rate_pct: null,
        avg_stock_return_pct: null,
        unable_reasons: {},
        breakdowns: {},
      });
      return;
    }
    await fulfillJson(route, {
      items: signals,
      total: signals.length,
      page: 1,
      page_size: 20,
    });
  });
}

async function createPortfolioAccount(page: Page, suffix: string) {
  const response = await page.request.post('/api/v1/portfolio/accounts', {
    data: {
      name: `Infrastructure ${suffix} ${Date.now()}`,
      broker: 'E2E',
      market: 'us',
      base_currency: 'USD',
    },
  });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json() as Promise<{ id: number }>;
}

async function selectPortfolioAccount(page: Page, accountId: number) {
  await page.goto('/portfolio');
  await expect(page.getByRole('heading', { name: '持仓管理' })).toBeVisible({ timeout: 15_000 });
  const accountSelect = page.getByRole('combobox', { name: '账户视图' });
  await accountSelect.click();
  await page.locator(`[role="option"][data-value="${accountId}"]`).click();
  await expect(page.getByRole('button', { name: '录入交易' })).toBeEnabled();
}

function historyItem(id: number, code: string, name: string) {
  return {
    id,
    query_id: `query-${id}`,
    stock_code: code,
    stock_name: name,
    report_type: 'full',
    report_language: 'zh',
    sentiment_score: 60,
    operation_advice: '观望',
    action: 'watch',
    trend_prediction: '震荡',
    analysis_summary: `${name} summary`,
    created_at: `2026-07-15T12:0${id}:00Z`,
    model_used: 'e2e/model',
  };
}

function historyDetail(id: number, code: string, name: string) {
  return {
    meta: {
      id,
      query_id: `query-${id}`,
      stock_code: code,
      stock_name: name,
      report_type: 'full',
      report_language: 'zh',
      created_at: `2026-07-15T12:0${id}:00Z`,
      model_used: 'e2e/model',
    },
    summary: {
      analysis_summary: `${name} semantic report`,
      operation_advice: '观望',
      trend_prediction: '震荡',
      sentiment_score: 60,
    },
    details: {},
  };
}

function signalItem(id: number, code: string, marker: string) {
  return {
    id,
    stock_code: code,
    stock_name: marker,
    market: 'us',
    source_type: 'analysis',
    trigger_source: 'e2e',
    action: 'watch',
    confidence: 0.8,
    score: 80,
    reason: `${marker} signal`,
    plan_quality: 'complete',
    status: 'active',
    created_at: '2026-07-15T12:00:00Z',
  };
}

function performance(code?: string) {
  return {
    scope: code ? 'stock' : 'overall',
    code,
    eval_window_days: 10,
    engine_version: 'e2e',
    total_evaluations: 1,
    completed_count: 1,
    insufficient_count: 0,
    long_count: 1,
    cash_count: 0,
    win_count: 1,
    loss_count: 0,
    neutral_count: 0,
    direction_accuracy_pct: 100,
    win_rate_pct: 100,
    advice_breakdown: {},
    diagnostics: {},
  };
}

function backtestRow(id: number, code: string) {
  return {
    analysis_history_id: id,
    code,
    stock_name: `${code} result`,
    analysis_date: '2026-07-15',
    eval_window_days: 10,
    engine_version: 'e2e',
    eval_status: 'completed',
    action: 'watch',
    trend_prediction: 'flat',
    direction_correct: true,
    outcome: 'win',
  };
}

async function assertRouteChrome(page: Page, path: string, text: string, title: string) {
  await page.goto(path);
  await expect(page.getByText(text, { exact: true }).first()).toBeVisible({ timeout: 15_000 });
  await expect(page).toHaveTitle(new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'));
}

async function assertNoDocumentOverflow(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState('domcontentloaded');
  await expect(page.locator('main')).toBeVisible({ timeout: 15_000 });
  await expect.poll(() => page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
  }))).toEqual({ viewport: 390, documentWidth: 390 });
}

test.describe('infrastructure interaction acceptance matrix', () => {
  test.use({ locale: 'zh-CN' });

  test('01 Chinese first-time login submits matching password confirmation', async ({ page }) => {
    const auth = await installMockAuth(page, { language: 'zh', passwordSet: false });
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: '设置初始密码' })).toBeVisible();
    await page.locator('#password').fill('first-login-password');
    await page.locator('#passwordConfirm').fill('first-login-password');
    await page.getByRole('button', { name: '完成设置并登录' }).click();
    await expect(page).toHaveURL('/');
    expect(auth.submitted()).toMatchObject({
      password: 'first-login-password',
      passwordConfirm: 'first-login-password',
    });
  });

  test('02 English first-time login renders and submits English setup flow', async ({ page }) => {
    const auth = await installMockAuth(page, { language: 'en', passwordSet: false });
    await page.goto('/login');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.getByRole('heading', { name: 'Set initial password' })).toBeVisible();
    await page.locator('#password').fill('first-login-password');
    await page.locator('#passwordConfirm').fill('first-login-password');
    await page.getByRole('button', { name: 'Finish setup and sign in' }).click();
    await expect(page).toHaveURL('/');
    expect(auth.submitted()).toMatchObject({ passwordConfirm: 'first-login-password' });
  });

  test('03 returning-user login error is localized and keeps diagnostic fallback out of primary copy', async ({ page }) => {
    await installMockAuth(page, {
      language: 'en',
      passwordSet: true,
      loginStatus: 401,
      loginError: {
        error: 'invalid_credentials',
        message: '服务器中文诊断：密码哈希不匹配',
        params: {},
        trace_id: 'login-e2e-trace',
      },
    });
    await page.goto('/login');
    await page.locator('#password').fill('wrong-password');
    await page.getByRole('button', { name: 'Enter workspace' }).click();
    await expect(page.getByText(/password|credentials/i).last()).toBeVisible();
    await expect(page.getByText('服务器中文诊断：密码哈希不匹配', { exact: true })).toHaveCount(0);
    await expect(page).toHaveURL(/\/login/);
  });

  test('03a authentication preserves canonical and legacy Discover URL ownership plus hash state', async ({ page }) => {
    test.setTimeout(60_000);
    const auth = await installMockAuth(page, {
      language: 'en',
      passwordSet: true,
    });
    await mockScreeningBase(page, []);
    const intentCases = [
      {
        entryPath: APP_ROUTE_PATHS.researchDiscover,
        input: {
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: 'custom_strategy_alpha',
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '17',
          source: 'notification',
        },
        expectedMarket: null,
        expectedStrategy: 'custom_strategy_alpha',
        expectedCount: '17',
      },
      {
        entryPath: LEGACY_ROUTE_PATHS.screening,
        input: {
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market]: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: String(RESEARCH_DISCOVER_DEFAULT_VALUES.count),
          source: 'notification',
        },
        expectedMarket: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
        expectedStrategy: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
        expectedCount: String(RESEARCH_DISCOVER_DEFAULT_VALUES.count),
      },
      {
        entryPath: LEGACY_ROUTE_PATHS.screening,
        input: {
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market]: 'unsupported',
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: '<bad>',
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '999',
          source: 'notification',
        },
        expectedMarket: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
        expectedStrategy: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
        expectedCount: String(RESEARCH_DISCOVER_DEFAULT_VALUES.count),
      },
    ] as const;

    for (const intentCase of intentCases) {
      auth.reset();
      const entryHref = `${intentCase.entryPath}?${new URLSearchParams(intentCase.input).toString()}#details`;
      await page.goto(entryHref);
      await expect(page).toHaveURL(/\/login\?redirect=/);
      const loginUrl = new URL(page.url());
      const redirectTarget = new URL(loginUrl.searchParams.get('redirect')!, loginUrl.origin);
      expect(redirectTarget.pathname).toBe(intentCase.entryPath);
      expect(redirectTarget.searchParams.get(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market))
        .toBe(intentCase.expectedMarket);
      expect(redirectTarget.searchParams.get(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy))
        .toBe(intentCase.expectedStrategy);
      expect(redirectTarget.searchParams.get(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count))
        .toBe(intentCase.expectedCount);
      expect(redirectTarget.searchParams.get('source')).toBe('notification');
      expect(redirectTarget.hash).toBe('#details');

      await page.locator('#password').fill('returning-user-password');
      await page.getByRole('button', { name: 'Enter workspace' }).click();
      await expect.poll(() => new URL(page.url()).pathname)
        .toBe(APP_ROUTE_PATHS.researchDiscover);

      const restoredUrl = new URL(page.url());
      expect(restoredUrl.searchParams.get(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market))
        .toBe(intentCase.expectedMarket);
      expect(restoredUrl.searchParams.get(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy))
        .toBe(intentCase.expectedStrategy);
      expect(restoredUrl.searchParams.get(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count))
        .toBe(intentCase.expectedCount);
      expect(restoredUrl.searchParams.get('source')).toBe('notification');
      expect(restoredUrl.hash).toBe('#details');
      const strategyControl = page.getByRole('combobox', { name: SCREENING_TEXT.en.selectStrategy });
      await expect(strategyControl).toHaveAttribute('data-value', intentCase.expectedStrategy);
      if (intentCase.expectedStrategy === 'custom_strategy_alpha') {
        await expect(strategyControl)
          .toContainText(`${SCREENING_TEXT.en.customStrategy} (custom_strategy_alpha)`);
      }
    }
  });

  test('04 UI language switch persists through refresh and browser back-forward navigation', async ({ page }) => {
    await login(page);
    await selectUiLanguage(page, 'en');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    expect(await page.evaluate((key) => localStorage.getItem(key), uiLanguageStorageKey)).toBe('en');
    await page.reload();
    await expect(page.getByRole('link', { name: 'Agent' })).toBeVisible();
    await page.getByRole('link', { name: 'Agent' }).click();
    await page.goBack();
    await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();
    await page.goForward();
    await expect(page.getByText('Ask Stock', { exact: true }).first()).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  });

  test('05 application routes render English chrome and localized document titles', async ({ page }) => {
    await login(page, 'en');
    await assertRouteChrome(page, APP_ROUTE_PATHS.home, UI_TEXT.en['home.todayFocus'], UI_TEXT.en['home.pageTitle']);
    await assertRouteChrome(page, APP_ROUTE_PATHS.agent, UI_TEXT.en['chat.title'], UI_TEXT.en['chat.pageTitle']);
    await assertRouteChrome(page, APP_ROUTE_PATHS.researchMarket, UI_TEXT.en['home.marketReview'], UI_TEXT.en['home.marketReviewPageTitle']);
    const navigation = page.getByRole('navigation', { name: UI_TEXT.en['layout.mainNav'] });
    const researchParent = navigation.getByRole('link', { name: UI_TEXT.en['layout.nav.research'] });
    const marketChild = navigation.getByRole('link', { name: UI_TEXT.en['home.marketReview'] });
    await expect(researchParent).not.toHaveAttribute('aria-current', 'page');
    await expect(marketChild).toHaveAttribute('aria-current', 'page');
    await expect(navigation.locator('a[aria-current="page"]')).toHaveCount(1);
    const researchToggle = navigation.getByRole('button', { name: UI_TEXT.en['layout.nav.research'] });
    await researchToggle.click();
    await expect(researchParent).toHaveAttribute('aria-current', 'page');
    await expect(marketChild).toBeHidden();
    await expect(navigation.locator('a[aria-current="page"]')).toHaveCount(1);
    await researchToggle.click();
    await expect(researchParent).not.toHaveAttribute('aria-current', 'page');
    await expect(marketChild).toHaveAttribute('aria-current', 'page');
    await assertRouteChrome(page, APP_ROUTE_PATHS.researchAnalysis, UI_TEXT.en['analysisWorkbench.title'], UI_TEXT.en['analysisWorkbench.documentTitle']);
    await assertRouteChrome(page, APP_ROUTE_PATHS.researchDiscover, SCREENING_TEXT.en.title, SCREENING_TEXT.en.documentTitle);
    await assertRouteChrome(page, APP_ROUTE_PATHS.portfolio, PORTFOLIO_TEXT.en.title, PORTFOLIO_TEXT.en.documentTitle);
    await assertRouteChrome(page, APP_ROUTE_PATHS.signals, UI_TEXT.en['decisionSignals.title'], UI_TEXT.en['decisionSignals.pageTitle']);
    const homeParent = navigation.getByRole('link', { name: UI_TEXT.en['layout.nav.home'] });
    const signalChild = navigation.getByRole('link', { name: UI_TEXT.en['layout.nav.decisionSignals'] });
    const homeToggle = navigation.getByRole('button', { name: UI_TEXT.en['layout.nav.home'] });
    await expect(homeParent).not.toHaveAttribute('aria-current', 'page');
    await expect(signalChild).toHaveAttribute('aria-current', 'page');
    await homeToggle.click();
    await expect(homeParent).toHaveAttribute('aria-current', 'page');
    await expect(signalChild).toBeHidden();
    await expect(navigation.locator('a[aria-current="page"]')).toHaveCount(1);
    await homeToggle.click();
    await expect(signalChild).toHaveAttribute('aria-current', 'page');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: UI_TEXT.en['layout.openNav'] }).click();
    const drawerNavigation = page.getByRole('dialog', { name: UI_TEXT.en['layout.navMenu'] })
      .getByRole('navigation', { name: UI_TEXT.en['layout.mainNav'] });
    const drawerHome = drawerNavigation.getByRole('link', { name: UI_TEXT.en['layout.nav.home'] });
    const drawerSignal = drawerNavigation.getByRole('link', { name: UI_TEXT.en['layout.nav.decisionSignals'] });
    await expect(drawerSignal).toHaveAttribute('aria-current', 'page');
    await drawerNavigation.getByRole('button', { name: UI_TEXT.en['layout.nav.home'] }).click();
    await expect(drawerHome).toHaveAttribute('aria-current', 'page');
    await expect(drawerSignal).toBeHidden();
    await expect(drawerNavigation.locator('a[aria-current="page"]')).toHaveCount(1);
    await page.getByRole('button', { name: UI_TEXT.en['common.closeDrawer'] }).click();
    await page.setViewportSize({ width: 1280, height: 720 });
    await assertRouteChrome(page, APP_ROUTE_PATHS.researchBacktest, BACKTEST_TEXT.en.runBacktest, BACKTEST_TEXT.en.documentTitle);
    await assertRouteChrome(page, usageSettingsHref, UI_TEXT.en['usage.title'], UI_TEXT.en['usage.title']);
    await assertRouteChrome(page, APP_ROUTE_PATHS.settings, UI_TEXT.en['settings.pageTitle'], UI_TEXT.en['settings.pageTitle']);
    await assertRouteChrome(page, '/missing-route', UI_TEXT.en['notFound.title'], UI_TEXT.en['notFound.pageTitle']);
  });

  test('05a legacy Usage deep links preserve context and replace into Settings', async ({ page }) => {
    await login(page, 'en');
    await page.goto(`${LEGACY_ROUTE_PATHS.usage}?period=today&section=legacy#recent`);

    await expect(page.getByRole('heading', {
      level: 2,
      name: UI_TEXT.en['usage.title'],
      exact: true,
    })).toBeVisible();
    await expect(page.locator('h1')).toHaveCount(1);
    const redirectedUrl = new URL(page.url());
    expect(redirectedUrl.pathname).toBe(APP_ROUTE_PATHS.settings);
    expect(redirectedUrl.searchParams.get('period')).toBe('today');
    expect(redirectedUrl.searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.section))
      .toBe(SETTINGS_SECTION_IDS.usage);
    expect(redirectedUrl.hash).toBe('#recent');
    await expect(page.getByRole('button', { name: 'Usage & cost' }))
      .toHaveAttribute('aria-current', 'page');
    await expect(page.getByRole('link', { name: 'Usage' })).toHaveCount(0);
  });

  test('05b legacy Research deep links preserve context and replace into canonical routes', async ({ page }) => {
    await login(page, 'en');

    for (const [legacyPath, canonicalPath] of [
      [LEGACY_ROUTE_PATHS.screening, APP_ROUTE_PATHS.researchDiscover],
      [LEGACY_ROUTE_PATHS.backtest, APP_ROUTE_PATHS.researchBacktest],
    ] as const) {
      await page.goto(`${legacyPath}?keep=yes#results`);
      await expect.poll(() => new URL(page.url()).pathname).toBe(canonicalPath);
      const redirectedUrl = new URL(page.url());
      expect(redirectedUrl.searchParams.get('keep')).toBe('yes');
      expect(redirectedUrl.hash).toBe('#results');

      await page.goBack();
      await expect.poll(() => new URL(page.url()).pathname).toBe(APP_ROUTE_PATHS.home);
    }
  });

  test('05c every explicit Discover URL intent survives canonical and legacy entry plus refresh', async ({ page }) => {
    await mockScreeningBase(page, [
      {
        id: 'dual_low',
        name: 'Dual low',
        name_en: 'Dual low',
        description_en: 'Default strategy',
        category_en: 'Value',
      },
      {
        id: 'quality',
        name: 'Quality',
        name_en: 'Quality',
        description_en: 'Stale task strategy',
        category_en: 'Quality',
      },
    ]);
    let restorationRequests = 0;
    await page.route('**/api/v1/alphasift/screen/tasks/stored-explicit-task', async (route) => {
      restorationRequests += 1;
      await fulfillJson(route, {
        task_id: 'stored-explicit-task',
        trace_id: 'stored-explicit-task',
        status: 'processing',
        progress: 40,
        message_code: 'task_processing',
        message_params: {},
        result: null,
      });
    });
    await login(page, 'en');

    const intentCases = [
      {
        name: 'safe custom strategy outside the preset catalog',
        input: {
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: 'custom_strategy_alpha',
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '17',
          source: 'notification',
        },
        expectedMarket: null,
        expectedStrategy: 'custom_strategy_alpha',
        expectedStrategyLabel: `${SCREENING_TEXT.en.customStrategy} (custom_strategy_alpha)`,
        expectedCount: '17',
      },
      {
        name: 'explicit default values',
        input: {
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market]: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: String(RESEARCH_DISCOVER_DEFAULT_VALUES.count),
          source: 'notification',
        },
        expectedMarket: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
        expectedStrategy: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
        expectedStrategyLabel: 'Dual low',
        expectedCount: String(RESEARCH_DISCOVER_DEFAULT_VALUES.count),
      },
      {
        name: 'known preset with non-default values',
        input: {
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market]: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: 'quality',
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '23',
          source: 'notification',
        },
        expectedMarket: null,
        expectedStrategy: 'quality',
        expectedStrategyLabel: 'Quality',
        expectedCount: '23',
      },
      {
        name: 'wholly malformed owned values',
        input: {
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market]: 'unsupported',
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: '<bad>',
          [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '999',
          source: 'notification',
        },
        expectedMarket: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
        expectedStrategy: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
        expectedStrategyLabel: 'Dual low',
        expectedCount: String(RESEARCH_DISCOVER_DEFAULT_VALUES.count),
      },
    ] as const;

    for (const entryPath of [APP_ROUTE_PATHS.researchDiscover, LEGACY_ROUTE_PATHS.screening]) {
      for (const intentCase of intentCases) {
        await test.step(`${entryPath}: ${intentCase.name}`, async () => {
          await page.evaluate(({ key, value }) => sessionStorage.setItem(key, JSON.stringify(value)), {
            key: screeningTaskStorageKey,
            value: {
              taskId: 'stored-explicit-task',
              market: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
              strategy: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
              maxResults: 8,
            },
          });
          const requestsBeforeNavigation = restorationRequests;
          const inputSearch = new URLSearchParams(intentCase.input).toString();
          await page.goto(`${entryPath}?${inputSearch}#details`);

          const assertIntentState = async () => {
            const currentUrl = new URL(page.url());
            expect(currentUrl.pathname).toBe(APP_ROUTE_PATHS.researchDiscover);
            expect(currentUrl.searchParams.get(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market))
              .toBe(intentCase.expectedMarket);
            expect(currentUrl.searchParams.get(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy))
              .toBe(intentCase.expectedStrategy);
            expect(currentUrl.searchParams.get(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count))
              .toBe(intentCase.expectedCount);
            expect(currentUrl.searchParams.get('source')).toBe('notification');
            expect(currentUrl.hash).toBe('#details');
            const strategyCombobox = page.getByRole('combobox', { name: SCREENING_TEXT.en.selectStrategy });
            await expect(strategyCombobox).toHaveAttribute('data-value', intentCase.expectedStrategy);
            await expect(strategyCombobox).toContainText(intentCase.expectedStrategyLabel);
            await page.getByRole('button', { name: SCREENING_TEXT.en.parameters }).click();
            await expect(page.getByRole('dialog', { name: SCREENING_TEXT.en.parameters })
              .getByLabel(SCREENING_TEXT.en.resultCount)).toHaveValue(intentCase.expectedCount);
            expect(await page.evaluate((key) => {
              const raw = sessionStorage.getItem(key);
              return raw ? JSON.parse(raw) : null;
            }, screeningTaskStorageKey)).toMatchObject({ taskId: 'stored-explicit-task' });
          };

          await expect.poll(() => new URL(page.url()).pathname).toBe(APP_ROUTE_PATHS.researchDiscover);
          await expect.poll(() => restorationRequests).toBeGreaterThan(requestsBeforeNavigation);
          await assertIntentState();
          const requestsBeforeReload = restorationRequests;
          await page.reload();
          await expect.poll(() => restorationRequests).toBeGreaterThan(requestsBeforeReload);
          await assertIntentState();
        });
      }
    }
  });

  test('06 Chinese UI with Chinese report keeps both report body and system actions Chinese', async ({ page }) => {
    await openSeededReport(page, 'zh', 'zh');
    await expect(page.getByText('核心洞察', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '完整分析报告' })).toBeVisible();
  });

  test('07 Chinese UI with English report renders English body and Chinese system actions', async ({ page }) => {
    await openSeededReport(page, 'zh', 'en');
    await expect(page.getByText('KEY INSIGHTS', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '完整分析报告' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Full analysis report' })).toHaveCount(0);
  });

  test('08 English UI with Chinese report renders Chinese body and English system actions', async ({ page }) => {
    await openSeededReport(page, 'en', 'zh');
    await expect(page.getByText('核心洞察', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Full analysis report' })).toBeVisible();
    await expect(page.getByRole('button', { name: '完整分析报告' })).toHaveCount(0);
  });

  test('09 English UI with English report keeps both report body and system actions English', async ({ page }) => {
    await openSeededReport(page, 'en', 'en');
    await expect(page.getByText('KEY INSIGHTS', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Full analysis report' })).toBeVisible();
  });

  test('10 report copy, diagnostics, and traceability chrome always follows UI language', async ({ page }) => {
    await openSeededReport(page, 'en', 'zh');
    await expect(page.getByText('Run Status', { exact: true })).toBeVisible();
    await expect(page.getByText('Data Traceability', { exact: true })).toBeVisible();
    await expect(page.getByText('运行状态', { exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Full Analysis Report' }).click();
    const drawer = page.getByRole('dialog', { name: /Full Analysis Report/ });
    await expect(drawer.getByRole('button', { name: 'Copy Markdown Source' })).toBeVisible();
    await expect(drawer.getByRole('button', { name: 'Copy Plain Text' })).toBeVisible();
  });

  test('11 Chat handles labeled input, IME composition, stream failure, and retry without duplicating the user message', async ({ page }) => {
    let streamAttempts = 0;
    await page.route('**/api/v1/agent/chat/stream', async (route) => {
      streamAttempts += 1;
      const body = streamAttempts === 1
        ? 'data: {"type":"error","error":"upstream_timeout","message":"raw upstream detail"}\n\n'
        : 'data: {"type":"progress","stage":"analysis","message":"streaming"}\n\ndata: {"type":"done","success":true,"content":"retry stream completed"}\n\n';
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body });
    });
    await login(page);
    await page.goto('/chat');
    const composer = page.getByRole('textbox', { name: '消息输入框' });
    await expect(composer).toBeVisible();
    await composer.fill('中文输入法不应提前发送');
    await composer.dispatchEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 229, isComposing: true });
    expect(streamAttempts).toBe(0);
    await page.getByRole('button', { name: '发送' }).click();
    await expect(page.getByRole('button', { name: '重试' })).toBeVisible();
    await expect(page.getByText('中文输入法不应提前发送', { exact: true })).toHaveCount(1);
    await page.getByRole('button', { name: '重试' }).click();
    await expect(page.getByText('retry stream completed', { exact: true })).toBeVisible();
    await expect(page.getByText('中文输入法不应提前发送', { exact: true })).toHaveCount(1);
    expect(streamAttempts).toBe(2);
  });

  test('12 Chat restores the URL session ahead of stale legacy storage and keeps it shareable', async ({ page }) => {
    await page.route('**/api/v1/agent/chat/sessions?**', (route) => fulfillJson(route, {
      sessions: [
        { session_id: 'url-session', title: 'URL session', message_count: 1, created_at: '2026-07-15T10:00:00Z', last_active: '2026-07-15T10:00:00Z' },
        { session_id: 'stale-local', title: 'Stale local', message_count: 1, created_at: '2026-07-14T10:00:00Z', last_active: '2026-07-14T10:00:00Z' },
      ],
    }));
    await page.route('**/api/v1/agent/chat/sessions/url-session', (route) => fulfillJson(route, {
      messages: [{ id: 'url-message', role: 'assistant', content: 'URL session restored' }],
    }));
    await page.route('**/api/v1/agent/chat/sessions/stale-local', (route) => fulfillJson(route, {
      messages: [{ id: 'stale-message', role: 'assistant', content: 'stale local message' }],
    }));
    await login(page);
    await page.evaluate(() => localStorage.setItem('dsa_chat_session_id', 'stale-local'));
    await page.goto('/chat?session=url-session');
    await expect(page).toHaveURL(/session=url-session/);
    await expect(page.getByText('URL session restored', { exact: true })).toBeVisible();
    await expect(page.getByText('stale local message', { exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => sessionStorage.getItem('dsa_chat_session_id'))).toBe('url-session');
    expect(await page.evaluate(() => localStorage.getItem('dsa_chat_session_id'))).toBeNull();
  });

  test('12b Chat keeps consumed report context in shared navigation without recreating the draft', async ({ page }) => {
    await page.route('**/api/v1/history/1', (route) => fulfillJson(
      route,
      historyDetail(1, 'AAPL', 'Apple'),
    ));
    await page.route('**/api/v1/agent/chat/stream', (route) => route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'data: {"type":"done","success":true,"content":"context preserved"}\n\n',
    }));
    await login(page);
    await page.goto('/chat?stock=AAPL&name=Apple&recordId=1');

    const composer = page.getByRole('textbox', { name: '消息输入框' });
    await expect(composer).toHaveValue('请深入分析 Apple(AAPL)');
    const sendButton = page.getByRole('button', { name: '发送' });
    await expect(sendButton).toBeEnabled();
    await sendButton.click();
    await expect(page.getByText('context preserved', { exact: true })).toBeVisible();
    await expect.poll(() => {
      const url = new URL(page.url());
      return Object.fromEntries(['stock', 'name', 'recordId', 'context'].map((key) => [
        key,
        url.searchParams.get(key),
      ]));
    }).toEqual({ stock: 'AAPL', name: 'Apple', recordId: '1', context: 'active' });

    const homeLink = page.getByRole('link', { name: '首页' });
    await expect(homeLink).toHaveAttribute('href', APP_ROUTE_PATHS.home);
    await homeLink.click();
    await expect.poll(() => {
      const url = new URL(page.url());
      return { pathname: url.pathname, stock: url.searchParams.get('stock'), recordId: url.searchParams.get('recordId') };
    }).toEqual({ pathname: '/', stock: null, recordId: null });
  });

  test('13 Screening displays a built-in strategy by stable ID in English', async ({ page }) => {
    await mockScreeningBase(page, [
      {
        id: 'bull_trend',
        name: '中文原始策略名',
        name_zh: '多头趋势',
        name_en: 'Bull Trend',
        description: 'raw description',
        description_zh: '捕捉多头趋势',
        description_en: 'Capture established bullish trends',
        category_zh: '趋势',
        category_en: 'Trend',
      },
      {
        id: 'dual_low',
        name: '中文双低原始名',
        name_en: 'Dual-low selection',
        description: 'raw dual-low description',
        description_en: 'Screens for candidates with relatively low price and valuation.',
        category_en: 'Value',
      },
    ]);
    await login(page, 'en');
    await page.goto(APP_ROUTE_PATHS.researchDiscover);

    const strategySelect = page.getByRole('combobox', { name: 'Select strategy' });
    await expect(strategySelect).toHaveAttribute('data-value', 'dual_low');
    await strategySelect.focus();
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Home');
    await page.keyboard.press('Enter');
    await expect(strategySelect).toHaveAttribute('data-value', 'bull_trend');
    await expect(page.getByText('中文原始策略名', { exact: true })).toHaveCount(0);
    await expect(page.getByText('Capture established bullish trends', { exact: true })).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    const parametersTrigger = page.getByRole('button', { name: 'Parameters' });
    await parametersTrigger.click();
    const dialog = page.getByRole('dialog', { name: 'Parameters' });
    await expect(dialog).toBeVisible();
    const dialogBox = await dialog.boundingBox();
    expect(dialogBox).not.toBeNull();
    expect(dialogBox!.x).toBeGreaterThanOrEqual(-1);
    expect(dialogBox!.x + dialogBox!.width).toBeLessThanOrEqual(391);
    expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(parametersTrigger).toBeFocused();
  });

  test('14 Screening restores a successful task and reports a subsequent failed task through the shared task contract', async ({ page }) => {
    await mockScreeningBase(page);
    let submissionAttempts = 0;
    await page.route('**/api/v1/alphasift/screen/tasks/restore-success', (route) => fulfillJson(route, {
      task_id: 'restore-success',
      status: 'completed',
      progress: 100,
      message_code: 'task_completed',
      message_params: {},
      result: screeningResult('RESTORED'),
    }));
    await page.route('**/api/v1/alphasift/screen/tasks/failing-task', (route) => fulfillJson(route, {
      task_id: 'failing-task',
      status: 'failed',
      progress: 80,
      message_code: 'task_failed',
      message_params: {},
      error: 'raw backend failure',
    }));
    await page.route('**/api/v1/alphasift/screen/tasks', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.fallback();
        return;
      }
      submissionAttempts += 1;
      if (submissionAttempts === 1) {
        await fulfillJson(route, {
          error: 'alphasift_screen_failed',
          message: 'raw task submission failure',
          params: {},
        }, 503);
        return;
      }
      await fulfillJson(route, {
        task_id: 'failing-task',
        status: 'pending',
        message: 'accepted',
        message_code: 'task_pending',
        message_params: {},
        strategy: 'bull_trend',
        market: 'cn',
        max_results: 20,
      });
    });
    await login(page);
    await page.evaluate(({ key, value }) => sessionStorage.setItem(key, JSON.stringify(value)), {
      key: screeningTaskStorageKey,
      value: { taskId: 'restore-success', market: 'cn', strategy: 'bull_trend', maxResults: 20 },
    });
    await page.goto(APP_ROUTE_PATHS.researchDiscover);
    await expect(page.getByText('RESTORED', { exact: true }).first()).toBeVisible();
    expect(await page.evaluate((key) => sessionStorage.getItem(key), screeningTaskStorageKey)).toBeNull();

    await page.setViewportSize({ width: 390, height: 844 });
    const resultsRegion = page.getByRole('region', { name: SCREENING_TEXT.zh.results });
    const collapseCandidate = page.getByRole('button', { name: SCREENING_TEXT.zh.collapse });
    const detailId = await collapseCandidate.getAttribute('aria-controls');
    expect(detailId).toBeTruthy();
    await expect(collapseCandidate).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator(`#${detailId}`)).toHaveAttribute(
      'aria-label',
      `RESTORED candidate ${SCREENING_TEXT.zh.details}`,
    );
    await collapseCandidate.focus();
    await page.keyboard.press('Enter');
    const expandCandidate = page.getByRole('button', { name: SCREENING_TEXT.zh.expand });
    await expect(expandCandidate).toHaveAttribute('aria-expanded', 'false');
    await expect(page.locator(`#${detailId}`)).toHaveCount(0);
    await expandCandidate.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator(`#${detailId}`)).toBeVisible();
    const tableDimensions = await resultsRegion.evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
    }));
    expect(tableDimensions.scrollWidth).toBeGreaterThan(tableDimensions.clientWidth);
    expect(await resultsRegion.evaluate((element) => {
      element.scrollLeft = element.scrollWidth;
      return element.scrollLeft;
    })).toBeGreaterThan(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);

    await page.getByRole('button', { name: '参数设置' }).click();
    const dialog = page.getByRole('dialog', { name: '参数设置' });
    await dialog.getByLabel('返回数量').press('Enter');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/外部行情或模型服务不可用，请稍后重试。/)).toBeVisible();
    await expect(dialog.getByText('raw task submission failure', { exact: true })).toHaveCount(0);

    await dialog.getByLabel('返回数量').press('Enter');
    await expect(dialog).toBeHidden();
    await expect(page.getByText('外部行情或模型服务不可用，请稍后重试。', { exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('raw backend failure', { exact: true })).toHaveCount(0);
    expect(submissionAttempts).toBe(2);
    await expect(page.getByText('RESTORED', { exact: true })).toHaveCount(0);
  });

  test('15 Alerts creation failure stays inside the modal and preserves all user input', async ({ page }) => {
    await mockEmptyAlertCollections(page);
    await page.route('**/api/v1/alerts/rules', async (route) => {
      if (route.request().method() === 'POST') {
        await fulfillJson(route, {
          error: 'alert_rule_create_failed',
          message: 'raw alert diagnostic',
          params: {},
        }, 500);
        return;
      }
      await route.fallback();
    });
    await login(page);
    await page.goto(LEGACY_ROUTE_PATHS.alerts);
    await page.getByRole('button', { name: '创建告警规则' }).click();
    const dialog = page.getByRole('dialog', { name: '创建告警规则' });
    await dialog.getByLabel('规则名称').fill('保留输入的失败规则');
    await dialog.getByLabel('标的代码').fill('AAPL');
    await dialog.getByLabel('价格阈值').fill('250');
    await dialog.getByRole('button', { name: '创建规则' }).click();
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/请求失败|创建失败/).first()).toBeVisible();
    await expect(dialog.getByLabel('规则名称')).toHaveValue('保留输入的失败规则');
    await expect(dialog.getByLabel('标的代码')).toHaveValue('AAPL');
    await expect(dialog.getByLabel('价格阈值')).toHaveValue('250');
  });

  test('16 Alerts keeps two rule mutations independently busy until each request settles', async ({ page }) => {
    const first = deferred();
    const second = deferred();
    await mockEmptyAlertCollections(page, [alertRule(1, 'Rule One'), alertRule(2, 'Rule Two')]);
    await page.route('**/api/v1/alerts/rules/*/disable', async (route) => {
      const id = Number(new URL(route.request().url()).pathname.split('/').at(-2));
      await (id === 1 ? first.promise : second.promise);
      await fulfillJson(route, { ...alertRule(id, id === 1 ? 'Rule One' : 'Rule Two'), enabled: false });
    });
    await login(page);
    await page.goto(LEGACY_ROUTE_PATHS.alerts);
    const rowOne = page.getByRole('row').filter({ hasText: 'Rule One' });
    const rowTwo = page.getByRole('row').filter({ hasText: 'Rule Two' });
    await rowOne.getByRole('button', { name: '停用' }).click();
    await rowTwo.getByRole('button', { name: '停用' }).click();
    const firstToggle = rowOne.getByRole('button', { name: '停用' });
    const secondToggle = rowTwo.getByRole('button', { name: '停用' });
    await expect(firstToggle).toBeDisabled();
    await expect(firstToggle).toHaveAttribute('aria-busy', 'true');
    await expect(firstToggle).toContainText('停用中');
    await expect(secondToggle).toBeDisabled();
    await expect(secondToggle).toHaveAttribute('aria-busy', 'true');
    await expect(secondToggle).toContainText('停用中');
    first.resolve();
    await expect(rowOne.locator('button[aria-busy="true"]')).toHaveCount(0);
    await expect(secondToggle).toBeDisabled();
    await expect(secondToggle).toHaveAttribute('aria-busy', 'true');
    second.resolve();
    await expect(rowTwo.locator('button[aria-busy="true"]')).toHaveCount(0);
  });

  test('16a Signal Center exposes four tabs and keeps scope in the URL', async ({ page }) => {
    await mockSignalCenterCollections(page);
    await login(page);
    await page.goto(APP_ROUTE_PATHS.signals);

    await expect(page.getByRole('heading', { name: '信号中心' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '信号流', exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: '规则', exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: '推送历史', exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: '再评估与统计', exact: true })).toBeVisible();

    await page.getByRole('button', { name: '持仓', exact: true }).click();
    await expect(page.getByRole('button', { name: '持仓', exact: true }))
      .toHaveAttribute('aria-pressed', 'true');
    await expect(page).toHaveURL(buildSignalCenterHref({
      scope: SIGNAL_CENTER_SCOPE_VALUES.holdings,
    }));

    await page.getByRole('tab', { name: '规则', exact: true }).click();
    await expect(page).toHaveURL(buildSignalCenterHref({
      scope: SIGNAL_CENTER_SCOPE_VALUES.holdings,
      tab: SIGNAL_CENTER_TAB_VALUES.rules,
    }));
    await expect(page.getByRole('button', { name: '创建告警规则' })).toBeVisible();

    await page.getByRole('tab', { name: '推送历史', exact: true }).click();
    await expect(page).toHaveURL(buildSignalCenterHref({
      scope: SIGNAL_CENTER_SCOPE_VALUES.holdings,
      tab: SIGNAL_CENTER_TAB_VALUES.history,
    }));
    await expect(page.getByRole('tab', { name: '触发历史', exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: '通知尝试记录', exact: true })).toBeVisible();
    await expect(page.getByRole('group', { name: '信号范围' })).toHaveCount(0);

    await page.getByRole('tab', { name: '再评估与统计', exact: true }).click();
    await expect(page).toHaveURL(buildSignalCenterHref({
      scope: SIGNAL_CENTER_SCOPE_VALUES.holdings,
      tab: SIGNAL_CENTER_TAB_VALUES.review,
    }));
    await expect(page.getByText('后验引擎', { exact: true })).toBeVisible();
    await expect(page.getByRole('group', { name: '信号范围' })).toHaveCount(0);
  });

  test('16b Signal Center maps legacy signal and alert URL state', async ({ page }) => {
    await mockSignalCenterCollections(page);
    await login(page);

    const legacyAlertsSearch = new URLSearchParams({
      [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: LEGACY_ALERTS_VIEW_VALUES.notifications,
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.watchlist,
      keep: 'yes',
    });
    await page.goto(`${LEGACY_ROUTE_PATHS.alerts}?${legacyAlertsSearch}#delivery`);
    await expect.poll(() => {
      const url = new URL(page.url());
      return {
        pathname: url.pathname,
        scope: url.searchParams.get(SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope),
        tab: url.searchParams.get(SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab),
        history: url.searchParams.get(SIGNAL_CENTER_ROUTE_QUERY_KEYS.history),
        keep: url.searchParams.get('keep'),
        hash: url.hash,
      };
    }).toEqual({
      pathname: APP_ROUTE_PATHS.signals,
      scope: SIGNAL_CENTER_SCOPE_VALUES.watchlist,
      tab: SIGNAL_CENTER_TAB_VALUES.history,
      history: SIGNAL_CENTER_HISTORY_VALUES.notifications,
      keep: 'yes',
      hash: '#delivery',
    });
    await expect(page.getByRole('tab', { name: '通知尝试记录', exact: true }))
      .toHaveAttribute('aria-selected', 'true');

    const legacyDecisionSignalsSearch = new URLSearchParams({
      [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: SIGNAL_FEED_VIEW_VALUES.stats,
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.holdings,
      keep: 'yes',
    });
    await page.goto(`${LEGACY_ROUTE_PATHS.decisionSignals}?${legacyDecisionSignalsSearch}`);
    await expect.poll(() => {
      const url = new URL(page.url());
      return {
        pathname: url.pathname,
        scope: url.searchParams.get(SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope),
        tab: url.searchParams.get(SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab),
        view: url.searchParams.get(SIGNAL_FEED_ROUTE_QUERY_KEYS.view),
        keep: url.searchParams.get('keep'),
      };
    }).toEqual({
      pathname: APP_ROUTE_PATHS.signals,
      scope: SIGNAL_CENTER_SCOPE_VALUES.holdings,
      tab: SIGNAL_CENTER_TAB_VALUES.review,
      view: null,
      keep: 'yes',
    });
    await expect(page.getByRole('tab', { name: '再评估与统计', exact: true }))
      .toHaveAttribute('aria-selected', 'true');
  });

  test('16c Signal Center empty feed opens the existing rule form', async ({ page }) => {
    await mockSignalCenterCollections(page);
    await login(page);
    await page.goto(APP_ROUTE_PATHS.signals);

    await page.getByRole('button', { name: '创建第一条规则' }).click();

    const dialog = page.getByRole('dialog', { name: '创建告警规则' });
    await expect(dialog).toBeVisible();
    await expect(page).toHaveURL(buildSignalCenterHref({
      tab: SIGNAL_CENTER_TAB_VALUES.rules,
    }));
    await dialog.getByRole('button', { name: '关闭' }).click();
    await expect(page.getByRole('tab', { name: '规则', exact: true }))
      .toHaveAttribute('aria-selected', 'true');
  });

  test('16d Portfolio signal summary deep-links to holdings scope', async ({ page }) => {
    await mockSignalCenterCollections(page);
    await login(page);
    await page.route('**/api/v1/portfolio/risk**', async (route) => {
      const response = await route.fetch();
      const body = await response.json() as JsonObject;
      await route.fulfill({
        response,
        json: {
          ...body,
          decision_signal_risk: {
            available: true,
            total: 0,
            actions: { sell: 0, reduce: 0, alert: 0 },
            items: [],
          },
        },
      });
    });
    const account = await createPortfolioAccount(page, 'signal-center-link');
    await selectPortfolioAccount(page, account.id);

    const portfolioIdentity = page.locator('[data-portfolio-switcher="single"]');
    await expect(portfolioIdentity).toHaveText('组合');
    await expect(portfolioIdentity.locator('button, [role="button"], select')).toHaveCount(0);

    const holdingsHref = buildSignalCenterHref({
      scope: SIGNAL_CENTER_SCOPE_VALUES.holdings,
    });
    const signalSummaryLink = page.locator(`a[href="${holdingsHref}"]`);
    await expect(signalSummaryLink).toHaveText('查看全部');
    await signalSummaryLink.click();

    await expect(page).toHaveURL(holdingsHref);
    const signalCenterHeading = page.getByRole('heading', { name: '信号中心' });
    await expect(signalCenterHeading).toBeVisible();
    await expect(signalCenterHeading).toBeFocused();
    await expect(page.getByRole('button', { name: '持仓', exact: true }))
      .toHaveAttribute('aria-pressed', 'true');
  });

  test('16e Signal Center reconciles stock context across browser history', async ({ page }) => {
    await mockSignalCenterCollections(page);
    await login(page);
    await page.goto(buildSignalCenterHref({ stock: 'AAPL' }));

    await expect(page.getByRole('button', { name: '当前查看：AAPL' })).toBeVisible();
    await page.getByRole('button', { name: '当前查看：AAPL' }).click();
    const dialog = page.getByRole('dialog', { name: '当前股票' });
    await dialog.getByRole('combobox', { name: '当前股票' }).fill('MSFT');
    await dialog.getByRole('button', { name: '查看股票' }).click();
    await expect(page).toHaveURL(buildSignalCenterHref({ stock: 'MSFT' }));
    await expect(page.getByRole('button', { name: '当前查看：MSFT' })).toBeVisible();

    await page.goBack();
    await expect(page).toHaveURL(buildSignalCenterHref({ stock: 'AAPL' }));
    await expect(page.getByRole('button', { name: '当前查看：AAPL' })).toBeVisible();

    await page.goForward();
    await expect(page).toHaveURL(buildSignalCenterHref({ stock: 'MSFT' }));
    await expect(page.getByRole('button', { name: '当前查看：MSFT' })).toBeVisible();
  });

  test('17 Portfolio timeout-after-commit retry reuses the operation ID and creates only one ledger row', async ({ page }) => {
    await login(page);
    const account = await createPortfolioAccount(page, 'idempotency');
    await selectPortfolioAccount(page, account.id);
    const operationIds: string[] = [];
    let firstAttempt = true;
    await page.route('**/api/v1/portfolio/trades', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue();
        return;
      }
      const payload = route.request().postDataJSON() as { operation_id: string };
      operationIds.push(payload.operation_id);
      if (firstAttempt) {
        firstAttempt = false;
        const committed = await route.fetch();
        expect(committed.ok(), await committed.text()).toBe(true);
        await fulfillJson(route, {
          error: 'upstream_timeout',
          message: 'simulated timeout after commit',
          params: {},
        }, 504);
        return;
      }
      await route.continue();
    });
    await page.getByRole('button', { name: '录入交易' }).click();
    const dialog = page.getByRole('dialog', { name: '手工录入：交易' });
    await dialog.getByLabel('股票代码').fill('AAPL');
    await dialog.getByLabel('数量').fill('2');
    await dialog.getByLabel('成交价').fill('210');
    await dialog.getByRole('button', { name: '提交交易' }).click();
    await expect(dialog.getByText('请求失败', { exact: true })).toBeVisible();
    await dialog.getByRole('button', { name: '提交交易' }).click();
    await expect(dialog).toBeHidden();
    expect(operationIds).toHaveLength(2);
    expect(operationIds[1]).toBe(operationIds[0]);
    const ledger = await page.request.get(`/api/v1/portfolio/trades?account_id=${account.id}&symbol=AAPL&page=1&page_size=20`);
    const ledgerBody = await ledger.json() as { total: number; items: unknown[] };
    expect(ledgerBody.total).toBe(1);
    expect(ledgerBody.items).toHaveLength(1);
  });

  test('18 Portfolio trade form is a usable single-column flow at 320px', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await login(page);
    const account = await createPortfolioAccount(page, 'mobile');
    await selectPortfolioAccount(page, account.id);
    await page.getByRole('button', { name: '录入交易' }).click();
    const dialog = page.getByRole('dialog', { name: '手工录入：交易' });
    const dateBox = await dialog.getByRole('textbox', { name: '交易日期', exact: true }).boundingBox();
    const sideBox = await dialog.getByRole('combobox', { name: '买卖方向' }).boundingBox();
    const submitBox = await dialog.getByRole('button', { name: '提交交易' }).boundingBox();
    expect(dateBox).not.toBeNull();
    expect(sideBox).not.toBeNull();
    expect(submitBox).not.toBeNull();
    expect(sideBox!.y).toBeGreaterThanOrEqual(dateBox!.y + dateBox!.height);
    expect(submitBox!.x).toBeGreaterThanOrEqual(0);
    expect(submitBox!.x + submitBox!.width).toBeLessThanOrEqual(320);
  });

  test('19 Model Access has one connection manager and no second provider credential form', async ({ page }) => {
    await openConnections(page);
    const main = page.locator('main');
    await expect(main.getByRole('button', { name: /添加模型服务/ })).toHaveCount(1);
    await expect(main.getByLabel('API 密钥')).toHaveCount(0);
    await expect(main.getByLabel('服务地址')).toHaveCount(0);
    await expect(main.getByText(/LLM_|LITELLM_/)).toHaveCount(0);
  });

  test('20 legacy Schema without AI placement fails safe to disabled Model Access and read-only diagnostics', async ({ page }) => {
    await login(page);
    await resetModelConfig(page);
    await page.route('**/api/v1/system/config?include_schema=true', async (route) => {
      const response = await route.fetch();
      const body = await response.json() as { items: Array<JsonObject> };
      const items = body.items.map((item) => {
        if (item.key !== 'LLM_CHANNELS') return item;
        const schema = { ...(item.schema as JsonObject) };
        delete schema.ui_placement;
        delete schema.uiPlacement;
        return { ...item, schema };
      });
      await route.fulfill({ response, json: { ...body, items } });
    });
    await page.goto(settingsHrefs.modelConnections);
    await expect(page.getByRole('button', { name: /添加模型服务/ })).toBeDisabled();
    await expect(page.getByLabel('API 密钥')).toHaveCount(0);
    await page.goto(settingsHrefs.advancedDiagnostics);
    await expect(page.getByText(/schema_ui_placement_missing/).first()).toBeVisible();
  });

  test('21 provider Catalog failure preserves a legacy official Connection identity', async ({ page }) => {
    await login(page);
    await configureConnections(page, [{ id: 'primary_gateway', model: 'shared-model' }]);
    await page.route('**/api/v1/system/config/llm/providers', (route) => fulfillJson(route, {}, 500));
    await page.goto(settingsHrefs.modelConnections);
    const card = page.getByTestId('connection-card-primary_gateway');
    await expect(card).toBeVisible();
    await expect(card).toContainText('openai');
    await expect(card).not.toContainText('自定义服务');
    await expect(page.getByText('模型服务列表加载失败')).toBeVisible();
  });

  test('22 the UI adds a second Connection for the same Provider without replacing the first', async ({ page }) => {
    await login(page);
    await configureConnections(page, [{ id: 'alpha_conn', model: 'model-alpha' }]);
    await page.goto(settingsHrefs.modelConnections);
    await expect(page.getByTestId('connection-card-alpha_conn')).toBeVisible();
    const secondConnectionId = await addOpenAiConnectionThroughUi(page, 'beta_conn', 'model-beta');
    await expect(page.getByTestId('connection-card-alpha_conn')).toContainText('OpenAI');
    await expect(page.getByText('beta_conn', { exact: true })).toBeVisible();
    await expect(page.getByText('OpenAI 官方', { exact: true })).toHaveCount(2);
    const config = await currentConfig(page);
    expect(secondConnectionId).not.toBe('alpha_conn');
    expect(config.items.find((item) => item.key === 'LLM_CHANNELS')?.value).toBe(`alpha_conn,${secondConnectionId}`);
    expect(config.items.find((item) => item.key === `LLM_${secondConnectionId.toUpperCase()}_PROVIDER`)?.value).toBe('openai');
  });

  test('23 same-name models from two Connections both appear in Task Routing with distinct ModelRefs', async ({ page }) => {
    await login(page);
    await configureConnections(page, [
      { id: 'alpha_conn', model: 'shared-model' },
      { id: 'beta_conn', model: 'shared-model' },
    ]);
    await page.goto(settingsHrefs.modelTaskRouting);
    await page.getByRole('button', { name: '主要模型', exact: true }).click();
    const alphaRef = encodeModelRef('alpha_conn', 'openai/shared-model');
    const betaRef = encodeModelRef('beta_conn', 'openai/shared-model');
    await expect(page.locator(`[role="option"][data-value="${alphaRef}"]`)).toBeVisible();
    await expect(page.locator(`[role="option"][data-value="${betaRef}"]`)).toBeVisible();
    expect(alphaRef).not.toBe(betaRef);
  });

  test('24 selecting a concrete Connection model persists and resolves that exact ModelRef', async ({ page }) => {
    await login(page);
    const alphaApiKey = process.env.DSA_WEB_E2E_ALPHA_API_KEY || randomBytes(32).toString('base64url');
    const betaApiKey = process.env.DSA_WEB_E2E_BETA_API_KEY || randomBytes(32).toString('base64url');
    await configureConnections(page, [
      { id: 'alpha_conn', model: 'shared-model', apiKey: alphaApiKey },
      { id: 'beta_conn', model: 'shared-model', apiKey: betaApiKey },
    ], [
      { key: 'GENERATION_BACKEND', value: 'litellm' },
      { key: 'GENERATION_FALLBACK_BACKEND', value: '' },
    ]);
    await page.goto(settingsHrefs.modelTaskRouting);
    const betaRef = encodeModelRef('beta_conn', 'openai/shared-model');
    const autosave = page.waitForResponse((response) => response.url().endsWith('/api/v1/system/config') && response.request().method() === 'PUT');
    await page.getByRole('button', { name: '主要模型', exact: true }).click();
    await page.locator(`[role="option"][data-value="${betaRef}"]`).click();
    expect((await autosave).status()).toBe(200);
    const config = await currentConfig(page);
    expect(config.items.find((item) => item.key === 'LITELLM_MODEL')?.value).toBe(betaRef);
    const available = await page.request.get('/api/v1/system/config/llm/available-models');
    const body = await available.json() as { models: Array<JsonObject> };
    expect(body.models).toContainEqual(expect.objectContaining({
      model_ref: betaRef,
      connection_id: 'beta_conn',
      route: 'openai/shared-model',
    }));

    const persistedByKey = new Map(config.items.map((item) => [item.key, item.value]));
    const smokeConfigKeys = [
      'GENERATION_BACKEND',
      'GENERATION_FALLBACK_BACKEND',
      'LLM_CONFIG_MODE',
      'LLM_CHANNELS',
      ...connectionItems('alpha_conn', 'shared-model').map((item) => item.key),
      ...connectionItems('beta_conn', 'shared-model').map((item) => item.key),
      'LITELLM_MODEL',
      'LITELLM_FALLBACK_MODELS',
    ];
    const persistedSmokeItems = smokeConfigKeys.map((key) => {
      const value = persistedByKey.get(key);
      expect(value, `persisted config is missing ${key}`).toBeDefined();
      return { key, value: value! };
    });
    expect(persistedByKey.get('GENERATION_BACKEND')).toBe('litellm');
    expect(persistedByKey.get('GENERATION_FALLBACK_BACKEND')).toBe('');
    expect(persistedByKey.get('LLM_CONFIG_MODE')).toBe('auto');
    expect(persistedByKey.get('LLM_CHANNELS')).toBe('alpha_conn,beta_conn');
    expect(persistedByKey.get('LITELLM_MODEL')).toBe(betaRef);
    expect(persistedByKey.get('LITELLM_FALLBACK_MODELS')).toBe('');
    for (const connectionId of ['ALPHA_CONN', 'BETA_CONN']) {
      expect(persistedByKey.get(`LLM_${connectionId}_PROTOCOL`)).toBe('openai');
      expect(persistedByKey.get(`LLM_${connectionId}_PROVIDER`)).toBe('openai');
      expect(persistedByKey.get(`LLM_${connectionId}_BASE_URL`)).toBe(fakeProviderBaseUrl);
      expect(persistedByKey.get(`LLM_${connectionId}_MODELS`)).toBe('shared-model');
      expect(persistedByKey.get(`LLM_${connectionId}_ENABLED`)).toBe('true');
    }
    for (const key of ['LLM_ALPHA_CONN_API_KEY', 'LLM_BETA_CONN_API_KEY']) {
      expect(config.items.find((item) => item.key === key)).toEqual(expect.objectContaining({
        value: config.mask_token,
        raw_value_exists: true,
        is_masked: true,
        schema: expect.objectContaining({ is_sensitive: true }),
      }));
    }

    await clearFakeProviderRequests(page);
    const smokeResponse = await page.request.post('/api/v1/system/config/generation-backends/smoke-test', {
      data: {
        backend_id: 'litellm',
        mode: 'json',
        items: persistedSmokeItems,
        mask_token: config.mask_token,
        timeout_seconds: 20,
      },
    });
    expect(smokeResponse.ok(), await smokeResponse.text()).toBe(true);
    const smokeBody = await smokeResponse.json() as { success: boolean; status: { backend_id: string } };
    expect(smokeBody).toEqual(expect.objectContaining({
      success: true,
      status: expect.objectContaining({ backend_id: 'litellm' }),
    }));

    const observed = await getFakeProviderRequests(page);
    const observedJson = JSON.stringify(observed);
    expect(observedJson.includes(alphaApiKey), 'provider records exposed the alpha credential').toBe(false);
    expect(observedJson.includes(betaApiKey), 'provider records exposed the beta credential').toBe(false);
    expect(observed.requests).toContainEqual(expect.objectContaining({
      method: 'POST',
      path: '/v1/chat/completions',
      authorization: true,
      authorization_sha256: authorizationFingerprint(betaApiKey),
    }));
    expect(observed.requests.some((request) => (
      request.authorization_sha256 === authorizationFingerprint(alphaApiKey)
    ))).toBe(false);
  });

  test('25 deleting a referenced Connection is rejected atomically by the backend', async ({ page }) => {
    await login(page);
    const alphaRef = encodeModelRef('alpha_conn', 'openai/shared-model');
    await configureConnections(page, [{ id: 'alpha_conn', model: 'shared-model' }], [
      { key: 'LITELLM_MODEL', value: alphaRef },
    ]);
    const response = await putConfigItems(page, [{ key: 'LLM_CHANNELS', value: '' }], 400);
    const body = await response.json() as { error: string; params: { issues: Array<JsonObject> } };
    expect(body.error).toBe('validation_failed');
    expect(body.params.issues).toContainEqual(expect.objectContaining({ code: 'model_in_use' }));
    const config = await currentConfig(page);
    expect(config.items.find((item) => item.key === 'LLM_CHANNELS')?.value).toBe('alpha_conn');
  });

  test('26 replacing a referenced same-name model removes only the target Connection model', async ({ page }) => {
    await login(page);
    const alphaRef = encodeModelRef('alpha_conn', 'openai/shared-model');
    const betaRef = encodeModelRef('beta_conn', 'openai/shared-model');
    await configureConnections(page, [
      { id: 'alpha_conn', model: 'shared-model,alpha-only' },
      { id: 'beta_conn', model: 'shared-model,beta-only' },
    ], [{ key: 'LITELLM_MODEL', value: alphaRef }]);
    await putConfigItems(page, [
      { key: 'LLM_ALPHA_CONN_MODELS', value: 'alpha-only' },
      { key: 'LITELLM_MODEL', value: betaRef },
    ]);
    const available = await page.request.get('/api/v1/system/config/llm/available-models');
    const body = await available.json() as { models: Array<{ model_ref: string }> };
    expect(body.models.some((entry) => entry.model_ref === alphaRef)).toBe(false);
    expect(body.models.some((entry) => entry.model_ref === betaRef)).toBe(true);
    expect(body.models.some((entry) => entry.model_ref === encodeModelRef('alpha_conn', 'openai/alpha-only'))).toBe(true);
    const config = await currentConfig(page);
    expect(config.items.find((item) => item.key === 'LITELLM_MODEL')?.value).toBe(betaRef);
  });

  test('27 Settings autosaves successfully and exposes no global Save action', async ({ page }) => {
    await login(page);
    await configureConnections(page, [{ id: 'alpha_conn', model: 'model-alpha' }]);
    await page.goto(settingsHrefs.modelConnections);
    const autosave = page.waitForResponse((response) => response.url().endsWith('/api/v1/system/config') && response.request().method() === 'PUT');
    await editConnectionAddModel(page, 'alpha_conn', 'model-autosaved');
    expect((await autosave).status()).toBe(200);
    await expect(page.getByText(/AI 模型: 已自动保存/)).toBeVisible();
    await expect(page.getByRole('button', { name: /保存配置/ })).toHaveCount(0);
    await page.reload();
    await expect(page.getByTestId('connection-card-alpha_conn')).toContainText('model-autosaved');
  });

  test('28 Settings autosave failure preserves draft, blocks leaving, and succeeds on explicit retry', async ({ page }) => {
    await login(page);
    await configureConnections(page, [{ id: 'alpha_conn', model: 'model-alpha' }]);
    await page.goto(settingsHrefs.modelConnections);
    await page.route('**/api/v1/system/config', async (route) => {
      if (route.request().method() === 'PUT') {
        await fulfillJson(route, { error: 'config_save_failed', message: 'raw save failure', params: {} }, 500);
        return;
      }
      await route.continue();
    });
    await editConnectionAddModel(page, 'alpha_conn', 'local-retry-model');
    await expect(page.getByText(/AI 模型: 自动保存失败/)).toBeVisible();
    await expect(page.getByTestId('connection-card-alpha_conn')).toContainText('local-retry-model');
    await page.getByRole('link', { name: '首页' }).click();
    const leaveDialog = page.getByRole('dialog', { name: '离开设置页？' });
    await expect(leaveDialog).toBeVisible();
    await leaveDialog.getByRole('button', { name: '取消' }).click();
    await page.unroute('**/api/v1/system/config');
    const retryResponse = page.waitForResponse((response) => response.url().endsWith('/api/v1/system/config') && response.request().method() === 'PUT');
    await page.getByRole('button', { name: '重试' }).first().click();
    expect((await retryResponse).status()).toBe(200);
    await expect(page.getByText(/AI 模型: 已自动保存/)).toBeVisible();
  });

  test('29 Settings 409 conflict exposes both versions and recovers by keeping the local draft', async ({ page }) => {
    await login(page);
    await configureConnections(page, [{ id: 'alpha_conn', model: 'model-alpha' }]);
    await page.goto(settingsHrefs.modelConnections);
    const baseConfig = await currentConfig(page);
    const baseModels = baseConfig.items.find((item) => item.key === 'LLM_ALPHA_CONN_MODELS')?.value;
    expect(baseModels).toBe('model-alpha');
    const observedStatuses: number[] = [];
    let submittedLocalModels = '';
    let conflictInjected = false;
    await page.route('**/api/v1/system/config', async (route) => {
      if (route.request().method() !== 'PUT' || conflictInjected) {
        await route.continue();
        return;
      }
      conflictInjected = true;
      const submitted = route.request().postDataJSON() as { items: Array<{ key: string; value: string }> };
      submittedLocalModels = submitted.items.find((item) => item.key === 'LLM_ALPHA_CONN_MODELS')?.value ?? '';
      await putConfigItems(page, [{ key: 'LLM_ALPHA_CONN_MODELS', value: 'server-model' }]);
      const response = await route.fetch();
      observedStatuses.push(response.status());
      await route.fulfill({ response });
    });
    await editConnectionAddModel(page, 'alpha_conn', 'local-conflict-model');
    await expect(page.getByRole('heading', { name: '配置同时被其他会话修改' })).toBeVisible();
    expect(observedStatuses).toEqual([409]);
    expect(submittedLocalModels).toBe('model-alpha,local-conflict-model');
    const conflict = page.locator('section').filter({ has: page.getByRole('heading', { name: '配置同时被其他会话修改' }) });
    await expect(conflict.getByText('server-model', { exact: true })).toBeVisible();
    await expect(conflict.getByText('model-alpha,local-conflict-model', { exact: true })).toBeVisible();
    const recovery = page.waitForResponse((response) => response.url().endsWith('/api/v1/system/config') && response.request().method() === 'PUT' && response.status() === 200);
    await page.getByRole('button', { name: '全部保留本地草稿' }).click();
    await recovery;
    await expect(page.getByText(/AI 模型: 已自动保存/)).toBeVisible();
    const config = await currentConfig(page);
    expect(config.items.find((item) => item.key === 'LLM_ALPHA_CONN_MODELS')?.value).toContain('local-conflict-model');
  });

  test('30 Model Access and Task Routing round-trip refreshes models and preserves navigation source', async ({ page }) => {
    await login(page);
    await resetModelConfig(page);
    await page.goto(settingsHrefs.modelTaskRouting);
    await page.getByRole('button', { name: '前往模型接入' }).click();
    await expect(page).toHaveURL(/view=connections&from=task_routing/);
    const connectionId = await addOpenAiConnectionThroughUi(page, 'alpha_conn', 'round-trip-model');
    await page.getByRole('button', { name: '返回任务路由' }).click();
    await expect(page).toHaveURL(/view=task_routing/);
    await page.getByRole('button', { name: '主要模型', exact: true }).click();
    const option = page.getByRole('option', { name: /round-trip-model.*alpha_conn/ });
    await expect(option).toBeVisible();
    await expect(option).toHaveAttribute('data-value', encodeModelRef(connectionId, 'openai/round-trip-model'));
    await page.goBack();
    await expect(page).toHaveURL(/view=connections/);
    await page.goForward();
    await expect(page).toHaveURL(/view=task_routing/);
  });

  test('31 Analysis Workbench keeps a submitted task trackable through SSE failure and polling completion', async ({ page }) => {
    let statusCalls = 0;
    await page.route('**/api/v1/analysis/tasks/stream', (route) => route.abort('connectionfailed'));
    await page.route('**/api/v1/analysis/analyze', async (route) => {
      await fulfillJson(route, {
        task_id: 'poll-fallback-task',
        trace_id: 'poll-fallback-trace',
        status: 'pending',
        message_code: 'task_pending',
        message_params: {},
      });
    });
    await page.route('**/api/v1/analysis/status/poll-fallback-task', async (route) => {
      statusCalls += 1;
      await fulfillJson(route, {
        task_id: 'poll-fallback-task',
        trace_id: 'poll-fallback-trace',
        status: 'completed',
        progress: 100,
        message_code: 'task_completed',
        message_params: {},
        stock_name: 'Polling Complete',
      });
    });
    await page.route('**/api/v1/analysis/tasks/poll-fallback-task/flow', async (route) => {
      await fulfillJson(route, {
        task_id: 'poll-fallback-task',
        trace_id: 'poll-fallback-trace',
        stock_code: 'AAPL',
        stock_name: 'Polling Complete',
        status: 'degraded',
        generated_at: '2026-07-15T10:00:00Z',
        summary: {
          elapsed_ms: 1200,
          failed_attempts: 1,
          fallback_count: 1,
          model: 'fixture-model',
          data_source_count: 1,
          event_count: 0,
        },
        lanes: [
          { id: 'entry', label: '入口', order: 1 },
          { id: 'data_source', label: '数据来源', order: 2 },
          { id: 'analysis', label: '分析引擎', order: 3 },
        ],
        nodes: [
          {
            id: 'task_queue',
            lane: 'entry',
            kind: 'queue',
            label: '任务队列',
            status: 'success',
          },
          {
            id: 'provider_realtime_quote_tickflowfetcher_1',
            lane: 'data_source',
            kind: 'data_source',
            label: '实时行情 · TickFlowFetcher',
            provider: 'TickFlowFetcher',
            status: 'failed',
            metadata: { data_type: 'realtime_quote', attempt: 1 },
          },
          {
            id: 'provider_realtime_quote_aksharefetcher_2',
            lane: 'data_source',
            kind: 'data_source',
            label: '实时行情 · AkshareFetcher',
            provider: 'AkshareFetcher',
            status: 'success',
            record_count: 1,
            metadata: { data_type: 'realtime_quote', attempt: 2 },
          },
          {
            id: 'context_pack',
            lane: 'analysis',
            kind: 'analysis',
            label: 'ContextPack',
            status: 'success',
          },
        ],
        edges: [
          {
            id: 'quote-fallback',
            from: 'provider_realtime_quote_tickflowfetcher_1',
            to: 'provider_realtime_quote_aksharefetcher_2',
            kind: 'fallback',
            status: 'success',
          },
        ],
        events: [],
      });
    });
    await login(page);
    await page.goto(APP_ROUTE_PATHS.researchAnalysis);
    const input = page.getByPlaceholder('输入股票代码或名称，如 600519、贵州茅台、AAPL');
    await input.fill('AAPL');
    await page.getByRole('tabpanel', { name: '发起与批量' })
      .getByRole('button', { name: '分析', exact: true })
      .click();
    const task = page.getByTestId('task-panel-item').filter({ hasText: 'AAPL' });
    await expect(task).toBeVisible();
    await expect(task.getByText('已完成', { exact: true })).toBeVisible({ timeout: 10_000 });
    expect(statusCalls).toBeGreaterThan(0);
    const runFlowButton = task.getByRole('button', { name: /查看.*运行流/ });
    await expect(runFlowButton).toHaveAttribute('data-control', 'icon-button');
    await expect(runFlowButton).toHaveAttribute('data-size', 'default');
    await runFlowButton.click();
    await expectMinimumTouchTarget(
      page.getByTestId('run-flow-node-topology_data_realtime_quote-toggle'),
    );
  });

  test('32 rapid history switching discards the older report response', async ({ page }) => {
    const oldReport = deferred();
    const oldRequestStarted = deferred();
    await page.route('**/api/v1/history**', async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/v1/history/stocks') {
        await fulfillJson(route, { total: 2, items: [historyItem(2, 'NEW', 'New Report'), historyItem(1, 'OLD', 'Old Report')] });
        return;
      }
      if (url.pathname === '/api/v1/history') {
        if (url.searchParams.get('report_type') === 'market_review') {
          await fulfillJson(route, { total: 0, page: 1, limit: 20, items: [] });
        } else {
          await fulfillJson(route, { total: 2, page: 1, limit: 20, items: [historyItem(2, 'NEW', 'New Report'), historyItem(1, 'OLD', 'Old Report')] });
        }
        return;
      }
      if (url.pathname === '/api/v1/history/1') {
        oldRequestStarted.resolve();
        await oldReport.promise;
        await fulfillJson(route, historyDetail(1, 'OLD', 'Old Report'));
        return;
      }
      if (url.pathname === '/api/v1/history/2') {
        await fulfillJson(route, historyDetail(2, 'NEW', 'New Report'));
        return;
      }
      await route.continue();
    });
    await login(page);
    await page.goto(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
    }));
    await expect(page.getByText('New Report semantic report', { exact: true })).toBeVisible();
    const oldItem = page.locator('.home-history-item').filter({ hasText: 'Old Report' }).first();
    const newItem = page.locator('.home-history-item').filter({ hasText: 'New Report' }).first();
    await oldItem.click();
    await oldRequestStarted.promise;
    await expect(newItem).toBeVisible();
    await newItem.click();
    await expect(page.getByText('New Report semantic report', { exact: true })).toBeVisible();
    oldReport.resolve();
    await page.waitForTimeout(200);
    await expect(page.getByText('New Report semantic report', { exact: true })).toBeVisible();
    await expect(page.getByText('Old Report semantic report', { exact: true })).toHaveCount(0);
  });

  test('33 starting a new Market Review generation invalidates the old in-flight poll', async ({ page }) => {
    const oldPoll = deferred();
    const oldPollStarted = deferred();
    let submissions = 0;
    let newReviewCompleted = false;
    const persistedReviewId = 33;
    await page.route('**/api/v1/history**', async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/v1/history' && url.searchParams.get('report_type') === 'market_review') {
        const items = newReviewCompleted
          ? [{
              ...historyItem(persistedReviewId, 'MARKET', 'Persisted New Market Review'),
              query_id: 'new-review-task',
              report_type: 'market_review',
              analysis_summary: 'NEW_GENERATION_PERSISTED',
            }]
          : [];
        await fulfillJson(route, { total: items.length, page: 1, limit: 10, items });
        return;
      }
      if (url.pathname === `/api/v1/history/${persistedReviewId}`) {
        await fulfillJson(route, {
          meta: {
            id: persistedReviewId,
            query_id: 'new-review-task',
            stock_code: 'MARKET',
            stock_name: 'Persisted New Market Review',
            report_type: 'market_review',
            report_language: 'zh',
            created_at: '2026-07-15T12:33:00Z',
            model_used: 'e2e/model',
          },
          summary: {
            analysis_summary: 'NEW_GENERATION_PERSISTED',
            operation_advice: '新一代持久化复盘',
            trend_prediction: '新一代结果',
            sentiment_score: 66,
          },
          details: {
            context_snapshot: {
              market_review_payload: {
                kind: 'market_review',
                region: 'cn',
                title: 'Persisted New Market Review',
                sections: [{
                  key: 'generation',
                  title: 'Generation',
                  markdown: 'NEW_GENERATION_PERSISTED',
                }],
              },
            },
          },
        });
        return;
      }
      await route.continue();
    });
    await page.route('**/api/v1/analysis/market-review', async (route) => {
      submissions += 1;
      await fulfillJson(route, {
        status: 'accepted',
        message: 'accepted',
        task_id: submissions === 1 ? 'old-review-task' : 'new-review-task',
        send_notification: false,
      }, 202);
    });
    await page.route('**/api/v1/analysis/status/old-review-task', async (route) => {
      oldPollStarted.resolve();
      await oldPoll.promise;
      await fulfillJson(route, {
        task_id: 'old-review-task', status: 'completed', progress: 100,
        market_review_report: 'OLD_GENERATION_SHOULD_NOT_RENDER',
      });
    });
    await page.route('**/api/v1/analysis/status/new-review-task', async (route) => {
      newReviewCompleted = true;
      await fulfillJson(route, {
        task_id: 'new-review-task', status: 'completed', progress: 100,
        market_review_report: 'NEW_RAW_STATUS_SHOULD_NOT_RENDER',
      });
    });
    await login(page);
    await page.goto(APP_ROUTE_PATHS.researchMarket);
    const marketReviewButton = page.getByRole('button', { name: '大盘复盘', exact: true }).first();
    await marketReviewButton.click();
    await expect.poll(() => submissions).toBe(1);
    await oldPollStarted.promise;
    // A second invocation can originate outside this page (for example from a
    // recovered task action). Trigger the same React action while the first
    // poll is in flight so the generation guard, not unmount cleanup, is what
    // rejects the old response.
    await expect(marketReviewButton).toBeEnabled();
    await marketReviewButton.click();
    await expect.poll(() => submissions).toBe(2);
    const persistedReport = page.getByTestId('market-review-report');
    await expect(persistedReport.getByText('NEW_GENERATION_PERSISTED', { exact: true })).toBeVisible();
    await expect(page).toHaveURL(`${APP_ROUTE_PATHS.researchMarket}?recordId=${persistedReviewId}`);
    await expect(page.getByText('NEW_RAW_STATUS_SHOULD_NOT_RENDER', { exact: true })).toHaveCount(0);
    oldPoll.resolve();
    await page.waitForTimeout(200);
    await expect(persistedReport.getByText('NEW_GENERATION_PERSISTED', { exact: true })).toBeVisible();
    await expect(page.getByText('OLD_GENERATION_SHOULD_NOT_RENDER', { exact: true })).toHaveCount(0);
  });

  test('34 Decision Signals rapid scope switch keeps only the latest stock response', async ({ page }) => {
    const oldLatest = deferred();
    await page.route('**/api/v1/decision-signals/**', async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith('/outcomes/stats')) {
        await fulfillJson(route, { total: 0, hit: 0, miss: 0, unable: 0, hit_rate_pct: 0, unable_reasons: {}, breakdowns: {} });
        return;
      }
      if (url.pathname.endsWith('/latest/OLD')) {
        await oldLatest.promise;
        await fulfillJson(route, { items: [signalItem(1, 'OLD', 'OLD_SCOPE')], total: 1, page: 1, page_size: 5 });
        return;
      }
      if (url.pathname.endsWith('/latest/NEW')) {
        await fulfillJson(route, { items: [signalItem(2, 'NEW', 'NEW_SCOPE')], total: 1, page: 1, page_size: 5 });
        return;
      }
      if (url.pathname === '/api/v1/decision-signals') {
        await fulfillJson(route, { items: [], total: 0, page: 1, page_size: 20 });
        return;
      }
      await fulfillJson(route, { items: [], total: 0, page: 1, page_size: 20 });
    });
    await login(page);
    await page.goto(LEGACY_ROUTE_PATHS.decisionSignals);
    await page.getByRole('button', { name: '当前股票' }).click();
    let dialog = page.getByRole('dialog', { name: '当前股票' });
    await dialog.getByRole('combobox', { name: '当前股票' }).fill('OLD');
    await dialog.getByRole('button', { name: '查看股票' }).click();
    await page.getByRole('button', { name: /当前查看：OLD/ }).click();
    dialog = page.getByRole('dialog', { name: '当前股票' });
    await dialog.getByRole('combobox', { name: '当前股票' }).fill('NEW');
    await dialog.getByRole('button', { name: '查看股票' }).click();
    await expect(page.getByText('NEW_SCOPE', { exact: true }).first()).toBeVisible();
    oldLatest.resolve();
    await page.waitForTimeout(200);
    await expect(page.getByText('NEW_SCOPE', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('OLD_SCOPE', { exact: true })).toHaveCount(0);
    await expect(page).toHaveURL(/stock=NEW/);
  });

  test('34b Decision Signals uses one canonical presentation across card, details, timeline, and Portfolio', async ({ page }) => {
    const canonicalSignal = {
      ...signalItem(91, 'AAPL', 'Canonical presentation fixture'),
      action: 'buy',
      action_label: 'Sell',
      confidence: 0.1,
      reason: 'Legacy summary must not render',
      risk_summary: 'Legacy risk must not render',
      created_at: '2026-01-01T00:00:00Z',
      presentation: {
        action: 'sell',
        label: 'Sell',
        confidence: 0.91,
        summary: 'Canonical momentum confirmed',
        risk: 'Canonical gap risk',
        timestamp: '2026-07-18T12:00:00Z',
      },
    };
    await page.route('**/api/v1/decision-signals**', async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith('/outcomes/stats')) {
        await fulfillJson(route, {
          total: 0,
          hit: 0,
          miss: 0,
          unable: 0,
          hit_rate_pct: 0,
          unable_reasons: {},
          breakdowns: {},
        });
        return;
      }
      if (url.pathname.endsWith('/outcomes')) {
        await fulfillJson(route, { items: [], total: 0, page: 1, page_size: 20 });
        return;
      }
      if (url.pathname.endsWith('/feedback')) {
        await fulfillJson(route, {
          signal_id: 91,
          feedback_value: null,
          reason_code: null,
          note: null,
          source: null,
          created_at: null,
          updated_at: null,
        });
        return;
      }
      await fulfillJson(route, {
        items: [canonicalSignal],
        total: 1,
        page: 1,
        page_size: 100,
      });
    });

    const applyStockContext = async () => {
      await page.getByRole('button', { name: 'Current stock' }).click();
      const dialog = page.getByRole('dialog', { name: 'Current stock' });
      await dialog.getByRole('combobox', { name: 'Current stock' }).fill('AAPL');
      await dialog.getByRole('button', { name: 'View stock' }).click();
    };

    await login(page, 'en');
    await page.goto(LEGACY_ROUTE_PATHS.decisionSignals);
    await applyStockContext();
    const latestPanel = page.getByRole('tabpanel', { name: 'Current stock' });
    await expect(latestPanel.getByText('Canonical momentum confirmed', { exact: true }).first()).toBeVisible();
    await expect(latestPanel.getByText('Canonical gap risk', { exact: true }).first()).toBeVisible();
    await expect(latestPanel.getByText('91%', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Sell', { exact: true })).toHaveCount(0);
    await expect(page.getByText('Legacy summary must not render', { exact: true })).toHaveCount(0);
    await expect(page.getByText('Legacy risk must not render', { exact: true })).toHaveCount(0);

    await page.getByRole('button', {
      name: 'View AI signal details for Canonical presentation fixture',
    }).first().click();
    const details = page.getByRole('dialog', { name: 'Signal details' });
    await expect(details).toBeVisible();
    await expect(details.getByText('Canonical momentum confirmed', { exact: true })).toBeVisible();
    await expect(details.getByText('Canonical gap risk', { exact: true })).toBeVisible();
    await expect(details.getByText('91%', { exact: true })).toBeVisible();
    await expect(details.getByText('Sell', { exact: true })).toHaveCount(0);
    await expect(details.getByText('Legacy summary must not render', { exact: true })).toHaveCount(0);
    await expect(details.getByText('Legacy risk must not render', { exact: true })).toHaveCount(0);

    await test.step('390px details keep canonical content within the viewport', async () => {
      const viewport = { width: 390, height: 844 };
      await page.setViewportSize(viewport);
      const box = await details.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(-1);
      expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
      await expect(details.getByText('Canonical momentum confirmed', { exact: true })).toBeVisible();
    });
    await test.step('320px details keep canonical content within the viewport', async () => {
      const viewport = { width: 320, height: 720 };
      await page.setViewportSize(viewport);
      const box = await details.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(-1);
      expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
      await expect(details.getByText('Canonical momentum confirmed', { exact: true })).toBeVisible();
    });
    await page.keyboard.press('Escape');
    await expect(details).toBeHidden();

    await page.getByRole('tab', { name: 'Stock signal timeline' }).click();
    const timelinePoint = page.getByTestId('timeline-hit-target-91');
    await expect(timelinePoint).toBeVisible();
    await timelinePoint.hover();
    await expect(page.getByText('Action: Buy', { exact: true })).toBeVisible();
    await expect(page.getByText('Confidence: 91%', { exact: true })).toBeVisible();

    await page.route('**/api/v1/portfolio/risk**', async (route) => {
      const response = await route.fetch();
      const body = await response.json() as JsonObject;
      await route.fulfill({
        response,
        json: {
          ...body,
          decision_signal_risk: {
            available: true,
            total: 1,
            actions: { sell: 1, reduce: 0, alert: 0 },
            items: [{
              account_id: null,
              symbol: 'AAPL',
              market: 'us',
              signal: {
                id: 91,
                action: 'sell',
                action_label: 'Buy',
                presentation: {
                  action: 'buy',
                  label: 'Buy',
                  confidence: 0.91,
                  summary: 'Canonical portfolio summary',
                  risk: 'Canonical portfolio risk',
                  timestamp: '2026-07-18T12:00:00Z',
                },
              },
            }],
          },
        },
      });
    });
    await createPortfolioAccount(page, 'canonical presentation');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/portfolio');
    await expect(page.getByRole('heading', { name: 'Portfolio management' })).toBeVisible();
    await expect(page.getByText('AAPL · Sell', { exact: true })).toBeVisible();
    await expect(page.getByText('AAPL · Buy', { exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
    await page.setViewportSize({ width: 320, height: 720 });
    await expect(page.getByText('AAPL · Sell', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
  });

  test('34c report and history use canonical action when legacy advice conflicts', async ({ page }) => {
    const conflictItem = {
      ...historyItem(92, 'AAPL', 'Canonical report fixture'),
      report_language: 'en',
      action: 'buy',
      action_label: 'Sell',
      operation_advice: 'Sell',
    };
    const conflictDetail = historyDetail(92, 'AAPL', 'Canonical report fixture');
    conflictDetail.meta.report_language = 'en';
    conflictDetail.summary = {
      ...conflictDetail.summary,
      action: 'buy',
      action_label: 'Sell',
      operation_advice: 'Sell',
    };

    await page.route('**/api/v1/history**', async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/v1/history/stocks') {
        await fulfillJson(route, { total: 1, items: [conflictItem] });
        return;
      }
      if (url.pathname === '/api/v1/history') {
        const items = url.searchParams.get('report_type') === 'market_review' ? [] : [conflictItem];
        await fulfillJson(route, { total: items.length, page: 1, limit: 20, items });
        return;
      }
      if (url.pathname === '/api/v1/history/92') {
        await fulfillJson(route, conflictDetail);
        return;
      }
      await route.continue();
    });

    await login(page, 'en');
    await page.goto(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
    }));
    const reportItem = page.getByRole('button', {
      name: 'Canonical report fixture AAPL history record',
      exact: true,
    });
    await expect(reportItem).toBeVisible({ timeout: 15_000 });
    await expect(reportItem.getByText('Buy 60', { exact: true })).toBeVisible();
    await expect(reportItem.getByText('Sell', { exact: true })).toHaveCount(0);

    await reportItem.click();
    const actionAdvice = page.getByText('Action Advice', { exact: true });
    await expect(actionAdvice).toBeVisible();
    await expect(actionAdvice.locator('..').getByText('Buy', { exact: true })).toBeVisible();
    await expect(page.getByText('Sell', { exact: true })).toHaveCount(0);
  });

  test('35 Backtest rapid result-filter switch keeps results and performance on the same latest phase', async ({ page }) => {
    const oldResults = deferred();
    const oldPerformance = deferred();
    await page.route('**/api/v1/backtest/**', async (route) => {
      const url = new URL(route.request().url());
      const phase = url.searchParams.get('analysis_phase');
      if (phase === 'intraday') {
        await (url.pathname.includes('/performance') ? oldPerformance.promise : oldResults.promise);
      }
      const marker = phase === 'intraday' ? 'OLD_INTRADAY' : phase === 'postmarket' ? 'NEW_POSTMARKET' : 'INITIAL';
      if (url.pathname === '/api/v1/backtest/results') {
        await fulfillJson(route, phase ? { total: 1, page: 1, limit: 20, items: [backtestRow(phase === 'intraday' ? 1 : 2, marker)] } : { total: 0, page: 1, limit: 20, items: [] });
        return;
      }
      if (url.pathname === '/api/v1/backtest/performance') {
        await fulfillJson(route, performance());
        return;
      }
      await fulfillJson(route, performance(marker));
    });
    await login(page);
    await page.goto(APP_ROUTE_PATHS.researchBacktest);
    const phase = page.getByRole('combobox', { name: /结果筛选.*阶段/ });
    await phase.click();
    await page.locator('[role="option"][data-value="intraday"]').click();
    await phase.click();
    await page.locator('[role="option"][data-value="postmarket"]').click();
    await expect(page.getByText('NEW_POSTMARKET', { exact: true }).first()).toBeVisible();
    oldResults.resolve();
    oldPerformance.resolve();
    await page.waitForTimeout(200);
    await expect(page.getByText('NEW_POSTMARKET', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('OLD_INTRADAY', { exact: true })).toHaveCount(0);
    await expect(page).toHaveURL(/phase=postmarket/);
  });

  test('36 overlay stack closes only the top ConfirmDialog before the underlying Drawer and restores focus', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.route('**/api/v1/agent/chat/sessions?**', (route) => fulfillJson(route, {
      sessions: [{ session_id: 'overlay-session', title: 'Overlay Session', message_count: 1, created_at: '2026-07-15T10:00:00Z', last_active: '2026-07-15T10:00:00Z' }],
    }));
    await page.route('**/api/v1/agent/chat/sessions/overlay-session', (route) => fulfillJson(route, { messages: [] }));
    await login(page);
    await page.goto('/chat?session=overlay-session');
    const historyButton = page.getByRole('button', { name: '历史对话' }).first();
    await historyButton.focus();
    await historyButton.click();
    const drawer = page.getByRole('dialog', { name: '历史对话' });
    await expect(drawer).toBeVisible();
    await drawer.getByRole('button', { name: '删除对话 Overlay Session' }).click();
    const confirm = page.getByRole('dialog', { name: '删除对话' });
    await expect(confirm).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(confirm).toBeHidden();
    await expect(drawer).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(drawer).toBeHidden();
    await expect(historyButton).toBeFocused();
  });

  test('37 Workbench history stays reachable and Chat mobile Drawer restores focus', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);
    await page.goto(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
    }));
    const historyItem = page.getByRole('button', { name: /E2E Fixture AAPL 历史记录/ });
    await expect(historyItem).toBeVisible();
    await historyItem.focus();
    await expect(historyItem).toBeFocused();
    await expect(page.getByRole('dialog', { name: '历史记录' })).toHaveCount(0);

    await page.goto('/chat');
    const chatHistory = page.getByRole('button', { name: '历史对话' }).first();
    await chatHistory.focus();
    await chatHistory.click();
    const drawer = page.getByRole('dialog', { name: '历史对话' });
    await expect(drawer.getByRole('button', { name: '关闭抽屉' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(drawer).toBeHidden();
    await expect(chatHistory).toBeFocused();
  });

  test('38 320px Home, Workbench, and Market Review keep their primary controls fully reachable', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await login(page);
    const core = page.getByTestId('home-core-blocks');
    await expect(core.getByRole('heading', { name: '今日焦点', exact: true })).toBeVisible();
    await expect(core.getByRole('heading', { name: '待办', exact: true })).toBeVisible();
    await expect(core.getByRole('heading', { name: '信号摘要', exact: true })).toBeVisible();
    const configurable = page.getByRole('button', { name: /可配置区/ });
    await expect(configurable).toBeVisible();
    const configurableBox = await configurable.boundingBox();
    expect(configurableBox).not.toBeNull();
    expect(configurableBox!.x).toBeGreaterThanOrEqual(0);
    expect(configurableBox!.x + configurableBox!.width).toBeLessThanOrEqual(320);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);

    await page.goto(APP_ROUTE_PATHS.researchAnalysis);
    const input = page.getByPlaceholder('输入股票代码或名称，如 600519、贵州茅台、AAPL');
    await input.fill('AAPL');
    const controls = [page.getByRole('tabpanel', { name: '发起与批量' })
      .getByRole('button', { name: '分析', exact: true })];
    for (const control of controls) {
      await expect(control).toBeVisible();
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(320);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);

    await page.goto(APP_ROUTE_PATHS.researchMarket);
    const marketReview = page.getByRole('button', { name: '大盘复盘', exact: true }).first();
    await expect(marketReview).toBeVisible();
    const marketReviewBox = await marketReview.boundingBox();
    expect(marketReviewBox).not.toBeNull();
    expect(marketReviewBox!.x).toBeGreaterThanOrEqual(0);
    expect(marketReviewBox!.x + marketReviewBox!.width).toBeLessThanOrEqual(320);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
  });

  test('39 every first-level page avoids critical document-level horizontal clipping at 390px', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);
    await assertNoDocumentOverflow(page, APP_ROUTE_PATHS.home);
    await expect(page.getByTestId('home-core-blocks').getByRole('region')).toHaveCount(3);
    await assertNoDocumentOverflow(page, buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
    }));
    const reportHeading = page.getByRole('heading', { name: 'E2E Fixture' });
    const reportBody = page.getByText('E2E_MARKDOWN_FIXTURE: deterministic report content.', { exact: true });
    await expect(reportHeading).toBeVisible();
    await expect(reportBody).toBeVisible();
    await expect.poll(async () => (await getElementContrast(reportHeading)).ratio).toBeGreaterThanOrEqual(3);
    await expect.poll(async () => (await getElementContrast(reportBody)).ratio).toBeGreaterThanOrEqual(4.5);
    await assertNoDocumentOverflow(page, APP_ROUTE_PATHS.agent);
    await assertNoDocumentOverflow(page, APP_ROUTE_PATHS.researchMarket);
    await assertNoDocumentOverflow(page, APP_ROUTE_PATHS.researchDiscover);
    await assertNoDocumentOverflow(page, APP_ROUTE_PATHS.portfolio);
    await assertNoDocumentOverflow(page, APP_ROUTE_PATHS.signals);
    await assertNoDocumentOverflow(page, APP_ROUTE_PATHS.researchBacktest);
    await assertNoDocumentOverflow(page, usageSettingsHref);
    await assertNoDocumentOverflow(page, APP_ROUTE_PATHS.settings);
    await assertNoDocumentOverflow(page, '/missing-responsive-route');
  });

  test('40 light and dark themes keep Home and Settings key content readable', async ({ page }, testInfo) => {
    await login(page);
    const homeText = page.getByRole('heading', { name: '今日焦点', exact: true });
    await selectTheme(page, '浅色');
    await expect(page.locator('html')).not.toHaveClass(/dark/);
    await expect(homeText).toBeVisible();
    await expect.poll(async () => (await getElementContrast(homeText)).ratio).toBeGreaterThanOrEqual(4.5);
    const homeLightContrast = await getElementContrast(homeText);

    await selectTheme(page, '深色');
    await expect(page.locator('html')).toHaveClass(/dark/);
    await expect(homeText).toBeVisible();
    await expect.poll(async () => (await getElementContrast(homeText)).ratio).toBeGreaterThanOrEqual(4.5);
    const homeDarkContrast = await getElementContrast(homeText);
    expect(homeDarkContrast).not.toEqual(homeLightContrast);

    await page.goto(settingsHrefs.modelConnections);
    const settingsHeading = page.getByRole('heading', { name: '系统设置' });
    const settingsBody = page.getByText('统一管理模型、数据源、通知、安全认证与导入能力。', { exact: true });
    await expect(settingsHeading).toBeVisible();
    await expect(settingsBody).toBeVisible();
    await expect(page.locator('html')).toHaveClass(/dark/);
    await expect.poll(async () => (await getElementContrast(settingsHeading)).ratio).toBeGreaterThanOrEqual(3);
    await expect.poll(async () => (await getElementContrast(settingsBody)).ratio).toBeGreaterThanOrEqual(4.5);
    const settingsDarkHeadingContrast = await getElementContrast(settingsHeading);
    const settingsDarkBodyContrast = await getElementContrast(settingsBody);

    await selectTheme(page, '浅色');
    await expect(page.locator('html')).not.toHaveClass(/dark/);
    await expect.poll(async () => (await getElementContrast(settingsHeading)).ratio).toBeGreaterThanOrEqual(3);
    await expect.poll(async () => (await getElementContrast(settingsBody)).ratio).toBeGreaterThanOrEqual(4.5);
    const settingsLightHeadingContrast = await getElementContrast(settingsHeading);
    const settingsLightBodyContrast = await getElementContrast(settingsBody);
    expect(settingsLightHeadingContrast).not.toEqual(settingsDarkHeadingContrast);
    expect(settingsLightBodyContrast).not.toEqual(settingsDarkBodyContrast);
    const contrastPath = testInfo.outputPath('acceptance-theme-contrast.json');
    await writeFile(
      contrastPath,
      `${JSON.stringify({
        home: { light: homeLightContrast, dark: homeDarkContrast },
        settings: {
          light: { heading: settingsLightHeadingContrast, body: settingsLightBodyContrast },
          dark: { heading: settingsDarkHeadingContrast, body: settingsDarkBodyContrast },
        },
      }, null, 2)}\n`,
      'utf8',
    );
    await testInfo.attach('acceptance-theme-contrast', {
      path: contrastPath,
      contentType: 'application/json',
    });
    await expect(page.getByRole('button', { name: /添加模型服务/ }).first()).toBeVisible();
  });

  test.describe('touch-capable control targets', () => {
    test.use({ hasTouch: true });

    test('41 Settings selectors and Chat switches keep 44px touch targets at 390px', async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await login(page);
      const alphaRef = encodeModelRef('alpha_conn', 'openai/model-alpha');
      const betaRef = encodeModelRef('beta_conn', 'openai/model-beta');
      await configureConnections(page, [
        { id: 'alpha_conn', model: 'model-alpha' },
        { id: 'beta_conn', model: 'model-beta' },
      ], [
        { key: 'LITELLM_MODEL', value: alphaRef },
        { key: 'LITELLM_FALLBACK_MODELS', value: betaRef },
      ]);

      await page.goto(settingsHrefs.modelTaskRouting);
      const primaryModel = page.getByRole('button', { name: '主要模型', exact: true });
      await expectMinimumTouchTarget(primaryModel);
      await primaryModel.click();
      const betaOption = page.locator(`[role="option"][data-value="${betaRef}"]`);
      await expectMinimumTouchTarget(betaOption);
      await page.keyboard.press('Escape');

      await page.goto(settingsHrefs.modelReliability);
      const fallbackSelector = page.getByRole('button', { name: '选择备用模型', exact: true });
      await expectMinimumTouchTarget(fallbackSelector);
      await expectMinimumTouchTarget(page.getByRole('button', { name: /移除模型 model-beta/ }));
      await fallbackSelector.click();
      const fallbackSearch = page.getByRole('textbox', { name: '搜索模型' });
      await expect(fallbackSearch).toHaveAttribute('data-size', 'comfortable');
      const fallbackSearchTarget = fallbackSearch.locator('..');
      await expectMinimumTouchTarget(fallbackSearchTarget);

      const fallbackSearchBox = await fallbackSearch.boundingBox();
      const fallbackSearchTargetBox = await fallbackSearchTarget.boundingBox();
      expect(fallbackSearchBox).not.toBeNull();
      expect(fallbackSearchTargetBox).not.toBeNull();
      expect(fallbackSearchBox!.height).toBeLessThan(44);
      const topGap = fallbackSearchBox!.y - fallbackSearchTargetBox!.y;
      const bottomGap = fallbackSearchTargetBox!.y + fallbackSearchTargetBox!.height
        - fallbackSearchBox!.y - fallbackSearchBox!.height;
      expect(Math.max(topGap, bottomGap)).toBeGreaterThan(0);
      const slopPoint = {
        x: fallbackSearchBox!.x + fallbackSearchBox!.width / 2,
        y: topGap > bottomGap
          ? fallbackSearchTargetBox!.y + topGap / 2
          : fallbackSearchBox!.y + fallbackSearchBox!.height + bottomGap / 2,
      };
      expect(await fallbackSearch.evaluate((element, point) => (
        document.elementFromPoint(point.x, point.y) === element.parentElement
      ), slopPoint)).toBe(true);
      await fallbackSearch.evaluate((element) => element.blur());
      await expect(fallbackSearch).not.toBeFocused();
      await page.touchscreen.tap(slopPoint.x, slopPoint.y);
      await expect(fallbackSearch).toBeFocused();

      const fallbackCheckbox = page.getByRole('checkbox', { name: /model-beta/ });
      await expectMinimumTouchTarget(fallbackCheckbox.locator('xpath=ancestor::label'));

      await page.goto(settingsHrefs.systemService);
      const logLevelSelect = page.getByRole('combobox', { name: '日志级别', exact: true });
      await expectMinimumTouchTarget(logLevelSelect);
      await logLevelSelect.click();
      await expectMinimumTouchTarget(page.locator('[role="option"][data-value="INFO"]'));
      await page.keyboard.press('Escape');

      await page.goto('/chat');
      await expectMinimumTouchTarget(page.getByRole('switch', { name: '上下文压缩' }));
    });
  });
});
