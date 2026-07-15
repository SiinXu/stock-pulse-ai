import { expect, test, type Page, type Response as PlaywrightResponse, type TestInfo } from '@playwright/test';
import { encodeModelRef } from '../src/utils/modelRef';
import { loginAsE2eAdmin } from './auth-fixture';

const fakeProviderPort = Number(process.env.DSA_WEB_SMOKE_PROVIDER_PORT || 18101);
const fakeProviderBaseUrl = `http://127.0.0.1:${fakeProviderPort}/v1`;
const fakeProviderRootUrl = `http://127.0.0.1:${fakeProviderPort}`;
const CUSTOM_CONNECTION_ID = 'custom';
const E2E_REPORT_REF = encodeModelRef(CUSTOM_CONNECTION_ID, 'openai/fake-report-model');
const E2E_AGENT_REF = encodeModelRef(CUSTOM_CONNECTION_ID, 'openai/fake-agent-model');
const E2E_VISION_REF = encodeModelRef(CUSTOM_CONNECTION_ID, 'openai/fake-vision-model');

interface ConfigResponseEvent {
  sequence: number;
  kind: 'put' | 'schema';
  response: PlaywrightResponse;
}

interface AutosaveMonitor {
  sequence: number;
  consumedPutSequence: number;
  consumedSchemaSequence: number;
  events: ConfigResponseEvent[];
}

const autosaveMonitors = new WeakMap<Page, AutosaveMonitor>();

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
  'LLM_CUSTOM_PROTOCOL',
  'LLM_CUSTOM_PROVIDER',
  'LLM_CUSTOM_DISPLAY_NAME',
  'LLM_CUSTOM_BASE_URL',
  'LLM_CUSTOM_API_KEY',
  'LLM_CUSTOM_API_KEYS',
  'LLM_CUSTOM_MODELS',
  'LLM_CUSTOM_ENABLED',
  'LLM_CUSTOM_EXTRA_HEADERS',
  'LLM_OPENAI_PROTOCOL',
  'LLM_OPENAI_PROVIDER',
  'LLM_OPENAI_DISPLAY_NAME',
  'LLM_OPENAI_BASE_URL',
  'LLM_OPENAI_API_KEY',
  'LLM_OPENAI_API_KEYS',
  'LLM_OPENAI_MODELS',
  'LLM_OPENAI_ENABLED',
  'LLM_OPENAI_EXTRA_HEADERS',
  'LLM_OPENAI2_PROTOCOL',
  'LLM_OPENAI2_PROVIDER',
  'LLM_OPENAI2_DISPLAY_NAME',
  'LLM_OPENAI2_BASE_URL',
  'LLM_OPENAI2_API_KEY',
  'LLM_OPENAI2_API_KEYS',
  'LLM_OPENAI2_MODELS',
  'LLM_OPENAI2_ENABLED',
  'LLM_OPENAI2_EXTRA_HEADERS',
  'LLM_PRIMARY_GATEWAY_PROTOCOL',
  'LLM_PRIMARY_GATEWAY_PROVIDER',
  'LLM_PRIMARY_GATEWAY_DISPLAY_NAME',
  'LLM_PRIMARY_GATEWAY_BASE_URL',
  'LLM_PRIMARY_GATEWAY_API_KEY',
  'LLM_PRIMARY_GATEWAY_API_KEYS',
  'LLM_PRIMARY_GATEWAY_MODELS',
  'LLM_PRIMARY_GATEWAY_ENABLED',
  'LLM_PRIMARY_GATEWAY_EXTRA_HEADERS',
  'LLM_OLLAMA_PROTOCOL',
  'LLM_OLLAMA_PROVIDER',
  'LLM_OLLAMA_DISPLAY_NAME',
  'LLM_OLLAMA_BASE_URL',
  'LLM_OLLAMA_API_KEY',
  'LLM_OLLAMA_API_KEYS',
  'LLM_OLLAMA_MODELS',
  'LLM_OLLAMA_ENABLED',
  'LLM_OLLAMA_EXTRA_HEADERS',
  'LITELLM_MODEL',
  'AGENT_LITELLM_MODEL',
  'VISION_MODEL',
  'LITELLM_FALLBACK_MODELS',
];

async function capture(page: Page, testInfo: TestInfo, name: string) {
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({ path, fullPage: true });
  await testInfo.attach(name, { path, contentType: 'image/png' });
}

async function selectTheme(page: Page, theme: '浅色' | '深色') {
  await page.getByRole('button', { name: '切换主题' }).first().click();
  await page.getByRole('menuitemradio', { name: theme, exact: true }).click();
  if (theme === '深色') {
    await expect(page.locator('html')).toHaveClass(/dark/);
  } else {
    await expect(page.locator('html')).not.toHaveClass(/dark/);
  }
}

async function login(page: Page) {
  await loginAsE2eAdmin(page);
}

async function resetModelConfig(page: Page) {
  const result = await page.evaluate(async (keys) => {
    const configResponse = await fetch('/api/v1/system/config');
    const config = await configResponse.json();
    const response = await fetch('/api/v1/system/config', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        config_version: config.config_version,
        mask_token: config.mask_token || '******',
        reload_now: true,
        items: keys.map((key) => ({
          key,
          value: key === 'LLM_CONFIG_MODE' ? 'auto' : '',
        })),
      }),
    });
    return { ok: response.ok, status: response.status, text: await response.text() };
  }, MODEL_KEYS_TO_RESET);
  expect(result.ok, `reset failed (${result.status}): ${result.text}`).toBe(true);
}

async function updateModelConfig(page: Page, items: Array<{ key: string; value: string }>) {
  const result = await page.evaluate(async (updates) => {
    const configResponse = await fetch('/api/v1/system/config');
    const config = await configResponse.json();
    const response = await fetch('/api/v1/system/config', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        config_version: config.config_version,
        mask_token: config.mask_token || '******',
        reload_now: true,
        items: updates,
      }),
    });
    return { ok: response.ok, status: response.status, text: await response.text() };
  }, items);
  expect(result.ok, `config seed failed (${result.status}): ${result.text}`).toBe(true);
}

async function openSettings(page: Page) {
  await login(page);
  await page.goto('/settings');
  await expect(page.getByRole('heading', { name: '系统设置' })).toBeVisible({ timeout: 15_000 });
}

function resetAutosaveMonitor(page: Page) {
  let monitor = autosaveMonitors.get(page);
  if (!monitor) {
    monitor = {
      sequence: 0,
      consumedPutSequence: 0,
      consumedSchemaSequence: 0,
      events: [],
    };
    autosaveMonitors.set(page, monitor);
    page.on('response', (response) => {
      const current = autosaveMonitors.get(page);
      if (!current) return;
      const url = new URL(response.url());
      if (url.pathname !== '/api/v1/system/config') return;
      const method = response.request().method();
      const kind = method === 'PUT'
        ? 'put'
        : method === 'GET' && url.searchParams.get('include_schema') === 'true'
          ? 'schema'
          : null;
      if (!kind) return;
      current.sequence += 1;
      current.events.push({ sequence: current.sequence, kind, response });
    });
  }
  monitor.events = [];
  monitor.consumedPutSequence = monitor.sequence;
  monitor.consumedSchemaSequence = monitor.sequence;
}

async function takeNextAutosave(page: Page) {
  const monitor = autosaveMonitors.get(page);
  expect(monitor, 'autosave monitor was not initialized').toBeDefined();
  await expect.poll(
    () => monitor!.events.some((event) => (
      event.kind === 'put' && event.sequence > monitor!.consumedPutSequence
    )),
    { timeout: 20_000 },
  ).toBe(true);
  const put = monitor!.events.find((event) => (
    event.kind === 'put' && event.sequence > monitor!.consumedPutSequence
  ))!;
  monitor!.consumedPutSequence = put.sequence;

  await expect.poll(
    () => monitor!.events.some((event) => (
      event.kind === 'schema'
      && event.sequence > put.sequence
      && event.sequence > monitor!.consumedSchemaSequence
    )),
    { timeout: 20_000 },
  ).toBe(true);
  const schema = monitor!.events.find((event) => (
    event.kind === 'schema'
    && event.sequence > put.sequence
    && event.sequence > monitor!.consumedSchemaSequence
  ))!;
  monitor!.consumedSchemaSequence = schema.sequence;
  return { response: put.response, refreshResponse: schema.response };
}

async function openConnections(page: Page, reset = true) {
  await login(page);
  if (reset) {
    await resetModelConfig(page);
  }
  await page.goto('/settings?section=ai_models&view=connections');
  await expect(page.getByRole('heading', { name: '模型接入' })).toBeVisible({ timeout: 15_000 });
  resetAutosaveMonitor(page);
}

async function openAddDialog(page: Page) {
  await page.getByRole('button', { name: /添加模型服务/ }).first().click();
  const dialog = page.getByRole('dialog', { name: '添加模型服务' });
  await expect(dialog).toBeVisible();
  return dialog;
}

async function chooseProvider(page: Page, id: string) {
  await page.getByLabel('选择模型服务商').click();
  const option = page.getByRole('option').filter({ has: page.locator(`[data-value="${id}"]`) });
  if (await option.count()) {
    await option.first().click();
  } else {
    await page.locator(`[role="option"][data-value="${id}"]`).click();
  }
  const nextButton = page.getByRole('button', { name: '下一步' });
  await expect(nextButton).toBeEnabled();
  await nextButton.click();
}

async function chooseProviderBySearch(page: Page, query: string, id: string) {
  await page.getByLabel('选择模型服务商').click();
  await page.getByRole('combobox', { name: /选择模型服务商/ }).fill(query);
  await page.locator(`[role="option"][data-value="${id}"]`).click();
  const nextButton = page.getByRole('button', { name: '下一步' });
  await expect(nextButton).toBeEnabled();
  await nextButton.click();
}

async function addManualModel(page: Page, model: string) {
  const button = page.getByRole('button', { name: /手动添加模型/ });
  if (await button.isVisible().catch(() => false)) {
    await button.click();
  }
  const input = page.getByLabel('手动添加模型');
  await input.fill(model);
  await input.press('Enter');
}

async function configureCustomDraft(page: Page, selectedModels = ['fake-report-model']) {
  const dialog = await openAddDialog(page);
  await chooseProviderBySearch(page, '自定义', 'custom');
  await page.getByLabel('连接名称').fill('e2e');
  await page.getByLabel('服务地址').fill(fakeProviderBaseUrl);
  await page.getByRole('button', { name: '获取模型' }).click();
  await expect(page.getByText(/已获取 3 个模型/)).toBeVisible({ timeout: 20_000 });
  await dialog.getByRole('button', { name: '选择模型' }).click();
  for (const model of selectedModels) {
    await page.getByRole('checkbox', { name: model }).check();
  }
  await dialog.getByLabel('搜索模型').press('Escape');
  await page.getByRole('button', { name: '添加到配置' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`)).toContainText('未保存');
}

async function configureOpenAiDraft(
  page: Page,
  name: string,
  model: string,
  baseUrl = fakeProviderBaseUrl,
) {
  const dialog = await openAddDialog(page);
  await chooseProvider(page, 'openai');
  await dialog.getByLabel('连接名称').fill(name);
  await dialog.getByLabel('API 密钥', { exact: true }).fill('e2e-openai-key');
  await dialog.getByRole('button', { name: '使用自定义服务地址' }).click();
  await dialog.getByLabel('服务地址').fill(baseUrl);
  await addManualModel(page, model);
  await dialog.getByRole('button', { name: '添加到配置' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId(`connection-card-${name}`)).toContainText('未保存');
}

interface SaveExpectation {
  channels?: string;
  providers?: Record<string, string>;
}

async function saveDraft(
  page: Page,
  expectation: SaveExpectation = {
    channels: CUSTOM_CONNECTION_ID,
    providers: { [CUSTOM_CONNECTION_ID]: 'custom' },
  },
) {
  await expect(page.getByRole('button', { name: /保存配置/ })).toHaveCount(0);
  const { response, refreshResponse } = await takeNextAutosave(page);
  expect(response.status()).toBe(200);
  expect(refreshResponse.status()).toBe(200);
  const refreshed = await refreshResponse.json();
  if (expectation.channels !== undefined) {
    expect(refreshed.items.find((item: { key: string }) => item.key === 'LLM_CHANNELS')?.value).toBe(expectation.channels);
  }
  for (const [connection, provider] of Object.entries(expectation.providers ?? {})) {
    const providerKey = `LLM_${connection.toUpperCase()}_PROVIDER`;
    expect(refreshed.items.find((item: { key: string }) => item.key === providerKey)?.value).toBe(provider);
  }
  for (const connection of (expectation.channels ?? '').split(',').filter(Boolean)) {
    if (await page.getByTestId(`connection-card-${connection}`).count()) {
      await expect(page.getByTestId(`connection-card-${connection}`)).not.toContainText('未保存', { timeout: 15_000 });
    }
  }
  await expect(page.getByText('已自动保存').last()).toBeVisible({ timeout: 15_000 });
  return {
    payload: response.request().postDataJSON() as { items: Array<{ key: string; value: string }> },
    refreshed,
  };
}

async function createSavedConnection(page: Page, selectedModels = ['fake-report-model', 'fake-agent-model', 'fake-vision-model']) {
  await openConnections(page, true);
  await configureCustomDraft(page, selectedModels);
  await saveDraft(page);
}

async function createTwoSavedOpenAiConnections(
  page: Page,
  model = 'fake-report-model',
  firstBaseUrl = fakeProviderBaseUrl,
) {
  await openConnections(page, true);
  await configureOpenAiDraft(page, 'openai', model, firstBaseUrl);
  await saveDraft(page, { channels: 'openai', providers: { openai: 'openai' } });
  await configureOpenAiDraft(page, 'openai2', model);
  await saveDraft(page, {
    channels: 'openai,openai2',
    providers: { openai: 'openai', openai2: 'openai' },
  });
}

async function selectStrictModel(page: Page, label: string, route: string) {
  await page.getByRole('button', { name: label, exact: true }).click();
  await page.locator(`[role="option"][data-value="${route}"]`).click();
}

test.describe('model access product convergence', () => {
  test.use({ locale: 'zh-CN' });

  test('01 AI & Models exposes exactly four product views', async ({ page }) => {
    await openConnections(page);
    for (const label of ['总览', '模型接入', '任务路由', '可靠性']) {
      await expect(page.getByRole('tab', { name: label })).toBeVisible();
    }
    await expect(page.getByRole('tab', { name: '高级' })).toHaveCount(0);
  });

  test('02 legacy provider URLs replace-redirect to Model Access', async ({ page }) => {
    await login(page);
    await page.goto('/settings?category=ai_model&sub=providers');
    await expect(page.getByRole('heading', { name: '模型接入' })).toBeVisible();
    await expect.poll(() => page.url()).toContain('section=ai_models');
    expect(page.url()).toContain('view=connections');
    expect(page.url()).not.toContain('sub=providers');
  });

  test('03 Model Access has the concise title, description, and one primary action', async ({ page }, testInfo) => {
    await openConnections(page);
    await selectTheme(page, '浅色');
    await expect(page.getByText('连接模型服务，并管理可用于报告、Agent 和视觉任务的模型。')).toBeVisible();
    await expect(page.getByRole('button', { name: /添加模型服务/ })).toHaveCount(1);
    await capture(page, testInfo, 'connections-empty-light');
  });

  test('04 Model Access removes generation-backend diagnostics from the first screen', async ({ page }) => {
    await openConnections(page);
    const main = page.locator('main');
    await expect(main.getByText('生成后端状态')).toHaveCount(0);
    await expect(main.getByText('主后端')).toHaveCount(0);
    await expect(main.getByText('备用后端')).toHaveCount(0);
  });

  test('[scenario 19] Model Access never renders a second Provider credential form', async ({ page }) => {
    await createSavedConnection(page);
    await expect(page.getByLabel('API 密钥', { exact: true })).toHaveCount(0);
    await expect(page.getByLabel('服务地址')).toHaveCount(0);
    await expect(page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`)).toContainText('fake-report-model');
  });

  test('[scenario 20] a legacy AI schema without placement fails safe into read-only diagnostics', async ({ page }) => {
    let interceptedConfigLoads = 0;
    await page.route('**/api/v1/system/config**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (
        request.method() !== 'GET'
        || url.pathname !== '/api/v1/system/config'
        || url.searchParams.get('include_schema') !== 'true'
      ) {
        await route.continue();
        return;
      }
      interceptedConfigLoads += 1;
      const response = await route.fetch();
      const payload = await response.json() as {
        items: Array<Record<string, unknown> & { schema?: Record<string, unknown> }>;
      };
      const template = payload.items.find((item) => item.schema?.category === 'ai_model');
      const schema = {
        ...(template?.schema ?? {}),
        key: 'LLM_E2E_MISSING_PLACEMENT',
        title: 'E2E Legacy Placement Field',
        category: 'ai_model',
        display_order: 999,
      };
      delete schema.ui_placement;
      delete schema.uiPlacement;
      payload.items.push({
        ...(template ?? {}),
        key: 'LLM_E2E_MISSING_PLACEMENT',
        value: 'legacy-value',
        raw_value_exists: true,
        is_masked: false,
        schema,
      });
      await route.fulfill({ response, json: payload });
    });

    await openConnections(page, false);
    expect(interceptedConfigLoads).toBeGreaterThan(0);
    await expect(page.getByLabel('E2E Legacy Placement Field', { exact: true })).toHaveCount(0);
    await page.goto('/settings?section=advanced&view=raw_config');
    const diagnostics = page.locator('details').filter({ hasText: '开发者诊断' });
    await diagnostics.locator('summary').click();
    const field = page.getByLabel('E2E Legacy Placement Field', { exact: true });
    await expect(field).toBeVisible();
    await expect(field).toBeDisabled();
    await expect(page.locator('#setting-LLM_E2E_MISSING_PLACEMENT-issue-0')).toContainText(/缺少 AI 字段归属/);
  });

  test('06 normal AI views contain no raw config keys or legacy terminology', async ({ page }) => {
    await openConnections(page);
    for (const label of ['总览', '模型接入', '任务路由', '可靠性']) {
      await page.getByRole('tab', { name: label }).click();
      const text = await page.locator('main').innerText();
      expect(text).not.toMatch(/LLM_|LITELLM_|GENERATION_BACKEND|模型供应商|快速添加渠道|渠道管理|Legacy Provider/);
    }
  });

  test('07 Add opens one modal with backend-catalog and custom providers', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await page.getByLabel('选择模型服务商').click();
    await expect(page.locator('[role="option"][data-value="openai"]')).toContainText('OpenAI 官方');
    await expect(page.locator('[role="option"][data-value="ollama"]')).toContainText('Ollama');
    await expect(page.locator('[role="option"][data-value="custom"]')).toContainText('自定义兼容服务');
    await expect(dialog).toBeVisible();
  });

  test('08 provider picker is searchable by provider metadata', async ({ page }) => {
    await openConnections(page);
    await openAddDialog(page);
    await page.getByLabel('选择模型服务商').click();
    await page.getByRole('combobox', { name: /选择模型服务商/ }).fill('local-runtime');
    await expect(page.locator('[role="option"][data-value="ollama"]')).toBeVisible();
    await expect(page.locator('[role="option"][data-value="openai"]')).toHaveCount(0);
  });

  test('08b provider selection waits for an explicit Next action', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await page.getByLabel('选择模型服务商').click();
    await page.locator('[role="option"][data-value="openai"]').click();
    await expect(dialog.getByLabel('选择模型服务商')).toBeVisible();
    await expect(dialog.getByLabel('连接名称')).toHaveCount(0);
    await expect(dialog.getByRole('button', { name: '取消' })).toBeVisible();
    const nextButton = dialog.getByRole('button', { name: '下一步' });
    await expect(nextButton).toBeEnabled();
    await nextButton.click();
    await expect(dialog.getByLabel('连接名称')).toBeVisible();
  });

  test('09 official providers hide protocol and default Base URL', async ({ page }, testInfo) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'openai');
    await expect(dialog.getByLabel('协议')).toHaveCount(0);
    await expect(dialog.getByLabel('服务地址')).toHaveCount(0);
    await expect(dialog.getByText('使用服务商官方地址')).toBeVisible();
    await expect(dialog.getByLabel('API 密钥', { exact: true })).toBeVisible();
    await capture(page, testInfo, 'add-openai-modal');
  });

  test('[scenario 22] a second OpenAI Connection persists the same explicit Provider identity', async ({ page }) => {
    await openConnections(page);
    await configureOpenAiDraft(page, 'openai', 'fake-report-model');
    await saveDraft(page, { channels: 'openai', providers: { openai: 'openai' } });

    const dialog = await openAddDialog(page);
    await dialog.getByLabel('选择模型服务商').click();
    const openAiOption = page.locator('[role="option"][data-value="openai"]');
    await expect(openAiOption).toContainText('已接入 1 条');
    await openAiOption.click();
    await dialog.getByRole('button', { name: '下一步' }).click();
    await dialog.getByLabel('连接名称').fill('openai2');
    await dialog.getByLabel('API 密钥', { exact: true }).fill('e2e-openai-key-2');
    await dialog.getByRole('button', { name: '使用自定义服务地址' }).click();
    await dialog.getByLabel('服务地址').fill(fakeProviderBaseUrl);
    await addManualModel(page, 'fake-agent-model');
    await dialog.getByRole('button', { name: '添加到配置' }).click();

    await saveDraft(page, {
      channels: 'openai,openai2',
      providers: { openai: 'openai', openai2: 'openai' },
    });
    const available = await page.evaluate(async () => (
      fetch('/api/v1/system/config/llm/available-models').then((response) => response.json())
    ));
    expect(available.models).toEqual(expect.arrayContaining([
      expect.objectContaining({
        route: 'openai/fake-report-model',
        connection_id: 'openai',
        connection_name: 'openai',
        provider_id: 'openai',
        provider_label: 'OpenAI 官方',
      }),
      expect.objectContaining({
        route: 'openai/fake-agent-model',
        connection_id: 'openai2',
        connection_name: 'openai2',
        provider_id: 'openai',
        provider_label: 'OpenAI 官方',
      }),
    ]));
  });

  test('[scenario 23] same-name models from two Connections both appear in Task Routing', async ({ page }) => {
    await createTwoSavedOpenAiConnections(page);
    const firstRef = encodeModelRef('openai', 'openai/fake-report-model');
    const secondRef = encodeModelRef('openai2', 'openai/fake-report-model');

    await page.getByRole('tab', { name: '任务路由' }).click();
    await page.getByRole('button', { name: '主要模型', exact: true }).click();
    await expect(page.locator(`[role="option"][data-value="${firstRef}"]`)).toContainText('openai');
    await expect(page.locator(`[role="option"][data-value="${secondRef}"]`)).toContainText('openai2');
    await expect(page.getByRole('option').filter({ hasText: 'fake-report-model' })).toHaveCount(2);
  });

  test('[scenario 24] selecting a Connection-aware model resolves through that exact Connection', async ({ page }) => {
    await createTwoSavedOpenAiConnections(page, 'fake-report-model', 'http://127.0.0.1:9/v1');
    const selectedRef = encodeModelRef('openai2', 'openai/fake-report-model');

    await page.getByRole('tab', { name: '任务路由' }).click();
    await selectStrictModel(page, '主要模型', selectedRef);
    await saveDraft(page, {
      channels: 'openai,openai2',
      providers: { openai: 'openai', openai2: 'openai' },
    });

    const saved = await page.evaluate(async () => fetch('/api/v1/system/config').then((response) => response.json()));
    expect(saved.items.find((item: { key: string }) => item.key === 'LITELLM_MODEL')?.value).toBe(selectedRef);

    const smoke = await page.evaluate(async () => {
      const response = await fetch('/api/v1/system/config/generation-backends/smoke-test', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          backend_id: 'litellm',
          mode: 'text',
          timeout_seconds: 20,
          items: [],
          mask_token: '******',
        }),
      });
      return { status: response.status, body: await response.json() };
    });
    expect(smoke.status).toBe(200);
    expect(smoke.body, JSON.stringify(smoke.body)).toMatchObject({ success: true });
  });

  test('09c renaming an OpenAI Connection preserves Provider identity and model metadata', async ({ page }) => {
    await openConnections(page);
    await configureOpenAiDraft(page, 'openai', 'fake-report-model');
    await saveDraft(page, { channels: 'openai', providers: { openai: 'openai' } });

    await page.getByTestId('connection-card-openai').getByRole('button', { name: '编辑' }).click();
    const dialog = page.getByRole('dialog', { name: '编辑模型服务' });
    await expect(dialog.getByLabel('连接 ID')).toHaveValue('openai');
    await expect(dialog.getByLabel('连接 ID')).toHaveAttribute('readonly', '');
    await dialog.getByLabel('连接名称').fill('Primary gateway');
    await dialog.getByRole('button', { name: '保存修改' }).click();
    await expect(page.getByTestId('connection-card-openai')).toContainText('Primary gateway');
    await expect(page.getByTestId('connection-card-openai')).toContainText('OpenAI 官方');
    await saveDraft(page, {
      channels: 'openai',
      providers: { openai: 'openai' },
    });

    const available = await page.evaluate(async () => (
      fetch('/api/v1/system/config/llm/available-models').then((response) => response.json())
    ));
    expect(available.models).toContainEqual(expect.objectContaining({
      route: 'openai/fake-report-model',
      model_ref: encodeModelRef('openai', 'openai/fake-report-model'),
      connection_id: 'openai',
      connection_name: 'Primary gateway',
      provider_id: 'openai',
      provider_label: 'OpenAI 官方',
    }));
  });

  test('10 Ollama hides API key and can reveal an address override', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'ollama');
    await expect(dialog.getByLabel('API 密钥', { exact: true })).toHaveCount(0);
    await dialog.getByRole('button', { name: '使用自定义服务地址' }).click();
    await expect(dialog.getByLabel('服务地址')).toHaveValue('http://127.0.0.1:11434');
  });

  test('10b Ollama discovers through api/tags and tests with an empty API key', async ({ page, request }) => {
    await request.delete(`${fakeProviderRootUrl}/__requests`);
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'ollama');
    await expect(dialog.getByLabel('API 密钥', { exact: true })).toHaveCount(0);
    await dialog.getByRole('button', { name: '使用自定义服务地址' }).click();
    await dialog.getByLabel('服务地址').fill(fakeProviderRootUrl);
    await dialog.getByRole('button', { name: '获取模型' }).click();
    await expect(dialog.getByText(/已获取 2 个模型/)).toBeVisible({ timeout: 20_000 });
    await dialog.getByRole('button', { name: '选择模型' }).click();
    await dialog.getByRole('checkbox', { name: 'llama3.2:latest' }).check();
    await dialog.getByLabel('搜索模型').press('Escape');
    await dialog.getByRole('button', { name: '测试连接' }).click();
    await expect(dialog.getByText(/连接成功.*ollama\/llama3\.2:latest/)).toBeVisible({ timeout: 30_000 });

    const auditResponse = await request.get(`${fakeProviderRootUrl}/__requests`);
    expect(auditResponse.ok()).toBe(true);
    const audit = await auditResponse.json();
    expect(audit.requests).toContainEqual(expect.objectContaining({
      method: 'GET',
      path: '/api/tags',
      authorization: false,
    }));
    expect(audit.requests).toEqual(expect.arrayContaining([
      expect.objectContaining({ method: 'POST', path: expect.stringMatching(/^\/api\/(chat|generate)$/) }),
    ]));
  });

  test('11 custom service exposes enum protocol, address, and key controls', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'custom');
    await expect(dialog.getByLabel('协议')).toHaveAttribute('role', 'combobox');
    await expect(dialog.getByLabel('服务地址')).toBeVisible();
    await expect(dialog.getByLabel('API 密钥', { exact: true })).toBeVisible();
  });

  test('11b a Provider without discovery exposes manual model input without a broken action', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'anthropic');
    await expect(dialog.getByRole('button', { name: '获取模型' })).toHaveCount(0);
    await expect(dialog.getByText('该服务暂不支持自动获取模型，请在下方手动添加模型 ID。')).toBeVisible();
    await expect(dialog.getByLabel('手动添加模型')).toBeVisible();
  });

  test('11c Custom without a Base URL is rejected by the backend and blocks the modal draft', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'custom');
    await dialog.getByLabel('API 密钥', { exact: true }).fill('e2e-custom-key');
    await addManualModel(page, 'fake-report-model');
    await expect(dialog.getByLabel('服务地址')).toHaveAttribute('aria-invalid', 'true');
    await expect(dialog.getByRole('button', { name: '添加到配置' })).toBeDisabled();

    const responsePromise = page.waitForResponse(
      (response) => response.url().endsWith('/api/v1/system/config/llm/test-channel')
        && response.request().method() === 'POST',
    );
    await dialog.getByRole('button', { name: '测试连接' }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    const result = await response.json();
    expect(result).toMatchObject({
      success: false,
      error_code: 'invalid_config',
      details: {
        issue_code: 'missing_base_url',
      },
    });
    await expect(dialog.getByText(/缺少服务地址|配置无效/).first()).toBeVisible();
  });

  test('12 localhost custom service follows backend empty-key contract', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'custom');
    await dialog.getByLabel('服务地址').fill(fakeProviderBaseUrl);
    await addManualModel(page, 'fake-report-model');
    await expect(dialog.getByLabel('API 密钥', { exact: true })).toHaveAttribute('placeholder', '本地服务可留空');
    await expect(dialog.getByRole('button', { name: '添加到配置' })).toBeEnabled();
  });

  test('13 discovery returns candidates without auto-selecting them', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'custom');
    await dialog.getByLabel('服务地址').fill(fakeProviderBaseUrl);
    await dialog.getByRole('button', { name: '获取模型' }).click();
    await expect(dialog.getByText('已选 0 / 3')).toBeVisible({ timeout: 20_000 });
    await expect(dialog.getByRole('button', { name: '选择模型' })).toHaveAttribute('aria-expanded', 'false');
    await expect(dialog.getByRole('button', { name: '添加到配置' })).toBeDisabled();
  });

  test('14 discovered models support search and explicit multi-selection', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'custom');
    await dialog.getByLabel('服务地址').fill(fakeProviderBaseUrl);
    await dialog.getByRole('button', { name: '获取模型' }).click();
    await expect(dialog.getByText('已选 0 / 3')).toBeVisible({ timeout: 20_000 });
    await dialog.getByRole('button', { name: '选择模型' }).click();
    await expect(dialog.getByRole('listbox', { name: '可选模型' })).toHaveAttribute('aria-multiselectable', 'true');
    await dialog.getByLabel('搜索模型').fill('vision');
    await expect(dialog.getByRole('checkbox', { name: 'fake-vision-model' })).toBeVisible();
    await expect(dialog.getByRole('checkbox', { name: 'fake-report-model' })).toHaveCount(0);
    await dialog.getByRole('checkbox', { name: 'fake-vision-model' }).check();
    await expect(
      dialog.getByTestId('model-multi-select').getByRole('button', { name: '移除模型 fake-vision-model' }),
    ).toBeVisible();
  });

  test('15 manual model input splits and deduplicates pasted-style lists', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'custom');
    await dialog.getByLabel('服务地址').fill(fakeProviderBaseUrl);
    await addManualModel(page, 'model-a, model-b\nmodel-a');
    await expect(dialog.getByRole('button', { name: '移除模型 model-a' })).toHaveCount(1);
    await expect(dialog.getByRole('button', { name: '移除模型 model-b' })).toHaveCount(1);
  });

  test('16 Back returns to provider selection inside the same modal', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'openai');
    await dialog.getByRole('button', { name: '上一步' }).click();
    await expect(dialog.getByLabel('选择模型服务商')).toBeVisible();
    await expect(page.getByRole('dialog', { name: '添加模型服务' })).toHaveCount(1);
  });

  test('17 Add to configuration schedules one grouped autosave', async ({ page }) => {
    await openConnections(page);
    let saves = 0;
    page.on('request', (request) => {
      if (request.url().endsWith('/api/v1/system/config') && request.method() === 'PUT') saves += 1;
    });
    await configureCustomDraft(page);
    expect(saves).toBe(0);
    await expect(page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`)).toContainText('未保存');
    await saveDraft(page);
    expect(saves).toBe(1);
  });

  test('[scenario 27] Settings autosaves one model-graph transaction without a global Save', async ({ page }) => {
    await openConnections(page);
    let saves = 0;
    page.on('request', (request) => {
      if (request.url().endsWith('/api/v1/system/config') && request.method() === 'PUT') saves += 1;
    });
    await configureCustomDraft(page);
    const { payload } = await saveDraft(page);
    expect(saves).toBe(1);
    expect(payload.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ key: 'LLM_CHANNELS', value: CUSTOM_CONNECTION_ID }),
      expect.objectContaining({ key: 'LLM_CUSTOM_MODELS', value: 'fake-report-model' }),
    ]));
    await expect(page.getByRole('button', { name: /保存配置/ })).toHaveCount(0);
    await page.reload();
    await expect(page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`)).toContainText('fake-report-model');
  });

  test('18b a Connection card shows Provider identity, enablement, and independent test status', async ({ page }) => {
    await createSavedConnection(page, ['fake-report-model']);
    const card = page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`);
    await expect(card.getByTestId('provider-avatar-custom')).toBeVisible();
    await expect(card).toContainText('自定义兼容服务');
    await expect(card.getByText('已启用', { exact: true })).toBeVisible();
    await expect(card.getByText('未测试', { exact: true })).toBeVisible();
    await card.getByRole('button', { name: '测试', exact: true }).click();
    await expect(card.getByText('测试通过', { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(card.getByText('已启用', { exact: true })).toBeVisible();
  });

  test('19 Edit reuses the connection modal and keeps the page compact', async ({ page }) => {
    await createSavedConnection(page);
    await page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`).getByRole('button', { name: '编辑' }).click();
    const dialog = page.getByRole('dialog', { name: '编辑模型服务' });
    await expect(dialog.getByLabel('连接名称')).toHaveValue('e2e');
    await expect(page.getByRole('dialog', { name: '编辑模型服务' })).toHaveCount(1);
  });

  test('20 clicking the model region reuses the modal and focuses model management', async ({ page }) => {
    await createSavedConnection(page);
    await page.getByRole('button', { name: '管理模型 e2e' }).click();
    const dialog = page.getByRole('dialog', { name: '编辑模型服务' });
    await expect(dialog.getByRole('button', { name: '获取模型' })).toBeFocused();
  });

  test('21 deleting an unreferenced connection requires confirmation', async ({ page }) => {
    await createSavedConnection(page);
    await page.getByRole('button', { name: '更多操作 e2e' }).click();
    await page.getByRole('menuitem', { name: '删除连接' }).click();
    const dialog = page.getByRole('dialog', { name: '删除连接？' });
    await expect(page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`)).toBeVisible();
    await dialog.getByRole('button', { name: '删除连接' }).click();
    await expect(page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`)).toHaveCount(0);
  });

  test('[scenario 25] deleting a referenced Connection is blocked by API and page workflow', async ({ page }) => {
    await createSavedConnection(page, ['fake-report-model', 'fake-agent-model']);
    await page.getByRole('tab', { name: '任务路由' }).click();
    await selectStrictModel(page, '主要模型', E2E_REPORT_REF);
    await saveDraft(page);

    const rejected = await page.evaluate(async () => {
      const before = await fetch('/api/v1/system/config').then((response) => response.json());
      const response = await fetch('/api/v1/system/config', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          config_version: before.config_version,
          mask_token: before.mask_token,
          reload_now: true,
          items: [{ key: 'LLM_CHANNELS', value: '' }],
        }),
      });
      const body = await response.json();
      const after = await fetch('/api/v1/system/config').then((nextResponse) => nextResponse.json());
      return { status: response.status, body, channels: after.items.find((item: { key: string }) => item.key === 'LLM_CHANNELS')?.value };
    });
    expect(rejected.status).toBe(400);
    expect(rejected.channels).toBe(CUSTOM_CONNECTION_ID);
    expect(rejected.body.details.issues).toEqual(expect.arrayContaining([
      expect.objectContaining({
        code: 'model_in_use',
        details: expect.objectContaining({
          route: 'openai/fake-report-model',
          referenced_by: expect.arrayContaining([
            expect.objectContaining({ task: 'report', key: 'LITELLM_MODEL' }),
          ]),
        }),
      }),
    ]));

    await page.getByRole('tab', { name: '模型接入' }).click();
    await page.getByRole('button', { name: '更多操作 e2e' }).click();
    await page.getByRole('menuitem', { name: '删除连接' }).click();
    const dialog = page.getByRole('dialog', { name: '无法直接删除连接' });
    await expect(dialog).toContainText('报告');
    await expect(page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`)).toBeVisible();
    await dialog.getByRole('button', { name: '前往任务路由替换' }).click();
    await expect(page.getByRole('heading', { name: '任务路由' })).toBeVisible();
    await expect(page.getByRole('button', { name: '主要模型', exact: true })).toHaveAttribute(
      'data-value',
      E2E_REPORT_REF,
    );
  });

  test('22 task routing empty state links to model access', async ({ page }) => {
    await openConnections(page);
    await page.getByRole('tab', { name: '任务路由' }).click();
    await expect(page.getByText('还没有可用模型')).toBeVisible();
    await page.getByRole('button', { name: '前往模型接入' }).click();
    await expect(page.getByRole('heading', { name: '模型接入' })).toBeVisible();
  });

  test('[scenario 30] Model Access and Task Routing survive round-trip navigation and refresh', async ({ page }) => {
    await openConnections(page);
    await page.getByRole('tab', { name: '任务路由' }).click();
    await expect(page.getByText('还没有可用模型')).toBeVisible();
    await page.getByRole('button', { name: '前往模型接入' }).click();
    await expect(page).toHaveURL(/section=ai_models&view=connections&from=task_routing/);
    await expect(page.getByRole('button', { name: '返回任务路由' })).toBeVisible();

    await page.goBack();
    await expect(page).toHaveURL(/section=ai_models&view=task_routing/);
    await expect(page.getByText('还没有可用模型')).toBeVisible();
    await page.goForward();
    await expect(page).toHaveURL(/section=ai_models&view=connections&from=task_routing/);
    await expect(page.getByRole('button', { name: '返回任务路由' })).toBeVisible();

    await configureCustomDraft(page, ['fake-report-model']);
    await saveDraft(page);
    await page.getByRole('button', { name: '返回任务路由' }).click();
    await expect(page).toHaveURL(/section=ai_models&view=task_routing/);
    await expect(page).not.toHaveURL(/from=task_routing/);
    await page.getByRole('button', { name: '主要模型', exact: true }).click();
    await expect(page.locator(`[role="option"][data-value="${E2E_REPORT_REF}"]`)).toBeVisible();
  });

  test('23 available-model API errors are distinct from empty state and retryable', async ({ page }) => {
    await login(page);
    await resetModelConfig(page);
    await page.route('**/api/v1/system/config/llm/available-models', (route) => route.fulfill({ status: 500, body: '{}' }));
    await page.goto('/settings?section=ai_models&view=task_routing');
    await expect(page.getByText(/可用模型加载失败/)).toBeVisible();
    await expect(page.getByRole('button', { name: /重试|重新加载/ })).toBeVisible();
    await expect(page.getByText('还没有可用模型')).toHaveCount(0);
  });

  test('24 task models use strict SearchableSelect controls', async ({ page }) => {
    await createSavedConnection(page);
    await page.getByRole('tab', { name: '任务路由' }).click();
    for (const label of ['主要模型', 'Agent 主要模型', 'Vision 模型']) {
      const trigger = page.getByRole('button', { name: label, exact: true });
      await expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');
      await trigger.click();
      await expect(page.locator(`[role="option"][data-value="${E2E_REPORT_REF}"]`)).toBeVisible();
      await page.getByRole('combobox', { name: new RegExp(label) }).press('Escape');
    }
    await expect(page.locator('input[aria-label="主要模型"]')).toHaveCount(0);
  });

  test('24b Report, Agent, and Vision selections persist exact catalog routes in one payload', async ({ page }) => {
    await createSavedConnection(page);
    await page.getByRole('tab', { name: '任务路由' }).click();
    await selectStrictModel(page, '主要模型', E2E_REPORT_REF);
    await selectStrictModel(page, 'Agent 主要模型', E2E_AGENT_REF);
    await selectStrictModel(page, 'Vision 模型', E2E_VISION_REF);
    const { payload, refreshed } = await saveDraft(page);
    const submitted = Object.fromEntries(payload.items.map((item) => [item.key, item.value]));
    expect(submitted).toMatchObject({
      LITELLM_MODEL: E2E_REPORT_REF,
      AGENT_LITELLM_MODEL: E2E_AGENT_REF,
      VISION_MODEL: E2E_VISION_REF,
    });
    const persisted = Object.fromEntries(
      refreshed.items.map((item: { key: string; value: string }) => [item.key, item.value]),
    );
    expect(persisted).toMatchObject({
      LITELLM_MODEL: E2E_REPORT_REF,
      AGENT_LITELLM_MODEL: E2E_AGENT_REF,
      VISION_MODEL: E2E_VISION_REF,
    });
  });

  test('25 selected task routes survive Available Models becoming stale', async ({ page }) => {
    await createSavedConnection(page);
    await page.getByRole('tab', { name: '任务路由' }).click();
    await selectStrictModel(page, '主要模型', E2E_REPORT_REF);
    await saveDraft(page);
    await page.route('**/api/v1/system/config/llm/available-models', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ models: [] }),
    }));
    await page.reload();
    await expect(page.getByText(/当前配置不可用.*openai\/fake-report-model/)).toBeVisible();
  });

  test('26 fallback models are searchable, deduplicated, and reorderable', async ({ page }) => {
    await createSavedConnection(page);
    await page.getByRole('tab', { name: '可靠性' }).click();
    await page.getByRole('button', { name: '选择备用模型' }).click();
    await page.getByLabel('搜索模型').fill('agent');
    await expect(page.getByRole('checkbox', { name: 'fake-agent-model' })).toBeVisible();
    await expect(page.getByRole('checkbox', { name: 'fake-vision-model' })).toHaveCount(0);
    await page.getByRole('checkbox', { name: 'fake-agent-model' }).check();
    await page.getByLabel('搜索模型').fill('vision');
    await page.getByRole('checkbox', { name: 'fake-vision-model' }).check();
    await page.getByLabel('搜索模型').press('Escape');
    await expect(page.getByRole('button', { name: '上移 fake-vision-model' })).toBeEnabled();
    await page.getByRole('button', { name: '上移 fake-vision-model' }).click();
    await expect(page.getByRole('button', { name: '上移 fake-vision-model' })).toBeDisabled();
    await page.getByRole('button', { name: '选择备用模型' }).click();
    await expect(page.getByRole('checkbox', { name: 'fake-vision-model' })).toBeChecked();
    await expect(page.getByRole('checkbox', { name: 'fake-vision-model' })).toHaveCount(1);
    await expect(page.getByRole('button', { name: '上移 fake-vision-model' })).toHaveCount(1);
  });

  test('[scenario 26] deleting a referenced same-name model changes only its target Connection', async ({ page }) => {
    await createTwoSavedOpenAiConnections(page);
    const targetReportRef = encodeModelRef('openai2', 'openai/fake-report-model');
    const replacementRef = encodeModelRef('openai2', 'openai/fake-agent-model');

    await page.getByRole('button', { name: '管理模型 openai2' }).click();
    let dialog = page.getByRole('dialog', { name: '编辑模型服务' });
    await addManualModel(page, 'fake-agent-model');
    await dialog.getByRole('button', { name: '保存修改' }).click();
    await saveDraft(page, {
      channels: 'openai,openai2',
      providers: { openai: 'openai', openai2: 'openai' },
    });

    await page.getByRole('tab', { name: '任务路由' }).click();
    await selectStrictModel(page, '主要模型', targetReportRef);
    await saveDraft(page, {
      channels: 'openai,openai2',
      providers: { openai: 'openai', openai2: 'openai' },
    });

    await page.getByRole('tab', { name: '模型接入' }).click();
    await page.getByRole('button', { name: '管理模型 openai2' }).click();
    dialog = page.getByRole('dialog', { name: '编辑模型服务' });
    await dialog.getByRole('button', { name: '移除模型 fake-report-model' }).click();
    await expect(dialog.getByText('无法直接删除模型')).toBeVisible();
    await dialog.getByRole('button', { name: '替代模型' }).click();
    await page.locator(`[role="option"][data-value="${replacementRef}"]`).click();
    await dialog.getByRole('button', { name: '替换引用并删除' }).click();
    await dialog.getByRole('button', { name: '保存修改' }).click();
    await saveDraft(page, {
      channels: 'openai,openai2',
      providers: { openai: 'openai', openai2: 'openai' },
    });

    await expect(page.getByTestId('connection-card-openai')).toContainText('fake-report-model');
    await expect(page.getByTestId('connection-card-openai2')).not.toContainText('fake-report-model');
    await page.getByRole('tab', { name: '任务路由' }).click();
    await expect(page.getByRole('button', { name: '主要模型', exact: true })).toHaveAttribute('data-value', replacementRef);
  });

  test('26b referenced model deletion replaces all task references in one grouped autosave', async ({ page }) => {
    await createSavedConnection(page);
    await page.getByRole('tab', { name: '可靠性' }).click();
    await page.getByRole('button', { name: '选择备用模型' }).click();
    await page.getByRole('checkbox', { name: 'fake-report-model' }).check();
    await page.getByLabel('搜索模型').press('Escape');
    await page.getByRole('tab', { name: '任务路由' }).click();
    await selectStrictModel(page, '主要模型', E2E_REPORT_REF);
    await selectStrictModel(page, 'Agent 主要模型', E2E_REPORT_REF);
    await selectStrictModel(page, 'Vision 模型', E2E_REPORT_REF);

    await page.getByRole('tab', { name: '模型接入' }).click();
    await page.getByRole('button', { name: '管理模型 e2e' }).click();
    const dialog = page.getByRole('dialog', { name: '编辑模型服务' });
    await dialog.getByRole('button', { name: '移除模型 fake-report-model' }).click();
    const conflict = dialog.getByRole('alert').filter({ hasText: '无法直接删除模型' });
    await expect(dialog.getByText('无法直接删除模型')).toBeVisible();
    for (const task of ['报告', 'Agent', 'Vision', '备用']) {
      await expect(conflict.getByText(task, { exact: true })).toBeVisible();
    }
    await expect(dialog.getByRole('button', { name: '移除模型 fake-report-model' })).toBeVisible();
    await dialog.getByRole('button', { name: '替代模型' }).click();
    await page.locator(`[role="option"][data-value="${E2E_AGENT_REF}"]`).click();
    await dialog.getByRole('button', { name: '替换引用并删除' }).click();
    await expect(dialog.getByText('无法直接删除模型')).toHaveCount(0);
    await expect(dialog.getByRole('button', { name: '移除模型 fake-report-model' })).toHaveCount(0);
    await dialog.getByRole('button', { name: '保存修改' }).click();

    const { payload } = await saveDraft(page);
    const submitted = Object.fromEntries(payload.items.map((item) => [item.key, item.value]));
    expect(submitted.LLM_CUSTOM_MODELS).toBe('fake-agent-model,fake-vision-model');
    expect(submitted).toMatchObject({
      LITELLM_MODEL: E2E_AGENT_REF,
      AGENT_LITELLM_MODEL: E2E_AGENT_REF,
      VISION_MODEL: E2E_AGENT_REF,
      LITELLM_FALLBACK_MODELS: E2E_AGENT_REF,
    });
  });

  test('26c group Reset cancels a scheduled Connection autosave', async ({ page }) => {
    await createSavedConnection(page);
    let putCount = 0;
    page.on('request', (request) => {
      if (request.url().endsWith('/api/v1/system/config') && request.method() === 'PUT') putCount += 1;
    });
    await page.getByRole('button', { name: '管理模型 e2e' }).click();
    const dialog = page.getByRole('dialog', { name: '编辑模型服务' });
    await addManualModel(page, 'unsaved-model');
    await dialog.getByRole('button', { name: '保存修改' }).click();
    await expect(page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`)).toContainText('unsaved-model');

    await page.getByRole('button', { name: '重置当前分组', exact: true }).click();
    const resetDialog = page.getByRole('dialog', { name: '放弃未保存的修改？' });
    await resetDialog.getByRole('button', { name: '放弃修改' }).click();
    await expect(page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`)).not.toContainText('unsaved-model');
    await page.waitForTimeout(900);
    expect(putCount).toBe(0);
  });

  test('[scenario 21] catalog failure preserves a legacy official Connection identity', async ({ page }) => {
    await openConnections(page);
    await updateModelConfig(page, [
      { key: 'LLM_CHANNELS', value: 'primary_gateway' },
      { key: 'LLM_PRIMARY_GATEWAY_DISPLAY_NAME', value: 'primary_gateway' },
      { key: 'LLM_PRIMARY_GATEWAY_PROVIDER', value: 'openai' },
      { key: 'LLM_PRIMARY_GATEWAY_PROTOCOL', value: 'openai' },
      { key: 'LLM_PRIMARY_GATEWAY_BASE_URL', value: fakeProviderBaseUrl },
      { key: 'LLM_PRIMARY_GATEWAY_API_KEY', value: 'e2e-openai-key' },
      { key: 'LLM_PRIMARY_GATEWAY_API_KEYS', value: '' },
      { key: 'LLM_PRIMARY_GATEWAY_MODELS', value: 'fake-report-model' },
      { key: 'LLM_PRIMARY_GATEWAY_ENABLED', value: 'true' },
    ]);
    await page.route('**/api/v1/system/config/llm/providers', (route) => route.fulfill({ status: 500, body: '{}' }));
    await page.reload();
    const card = page.getByTestId('connection-card-primary_gateway');
    await expect(card).toBeVisible();
    await expect(card).toContainText('openai');
    await expect(card).not.toContainText('自定义服务');
    await expect(card).not.toContainText('草稿 · 未完成');
    await expect(card).not.toContainText('缺少服务地址');
    await expect(page.getByText('模型服务列表加载失败')).toBeVisible();
    await expect(page.getByRole('button', { name: '重试' })).toBeVisible();
  });

  test('28 developer diagnostics is top-level and collapsed by default', async ({ page }, testInfo) => {
    await openSettings(page);
    await page.goto('/settings?section=advanced&view=raw_config');
    const details = page.locator('details').filter({ hasText: '开发者诊断' });
    await expect(details).not.toHaveAttribute('open', '');
    await details.locator('summary').click();
    await expect(details).toHaveAttribute('open', '');
    await expect(details).toContainText(/模型配置生效来源|执行后端/);
    await capture(page, testInfo, 'developer-diagnostics-expanded');
  });

  test('[scenario 28] failed autosave retries its group and guards navigation while dirty', async ({ page }) => {
    await openConnections(page);
    let saveAttempts = 0;
    await page.route('**/api/v1/system/config', async (route) => {
      if (route.request().method() !== 'PUT') {
        await route.continue();
        return;
      }
      saveAttempts += 1;
      if (saveAttempts === 1) {
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'autosave_unavailable', message: 'temporary autosave failure' }),
        });
        return;
      }
      await route.continue();
    });

    await configureCustomDraft(page);
    await expect(page.getByText('自动保存失败')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: /保存配置/ })).toHaveCount(0);
    const card = page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`);
    await expect(card).toContainText('fake-report-model');
    await expect(card).toContainText('未保存');

    await page.getByRole('link', { name: '首页' }).click();
    const leaveDialog = page.getByRole('dialog', { name: '离开设置页？' });
    await expect(leaveDialog).toBeVisible();
    await leaveDialog.getByRole('button', { name: '取消' }).click();
    await expect(page).toHaveURL(/\/settings/);

    const retryResponse = page.waitForResponse(
      (response) => response.url().endsWith('/api/v1/system/config')
        && response.request().method() === 'PUT'
        && response.status() === 200,
    );
    await page.getByRole('alert').getByRole('button', { name: '重试此分组', exact: true }).click();
    const retry = await retryResponse;
    const retriedItems = Object.fromEntries(
      (retry.request().postDataJSON() as { items: Array<{ key: string; value: string }> }).items
        .map((item) => [item.key, item.value]),
    );
    expect(retriedItems).toMatchObject({
      LLM_CHANNELS: CUSTOM_CONNECTION_ID,
      LLM_CUSTOM_MODELS: 'fake-report-model',
    });
    await expect(page.getByText('已自动保存').last()).toBeVisible({ timeout: 15_000 });
    expect(saveAttempts).toBe(2);

    await page.reload();
    await expect(card).toContainText('fake-report-model');
    await expect(card).not.toContainText('未保存');

    await page.getByRole('link', { name: '首页' }).click();
    await expect(page).toHaveURL(/\/$/);
  });

  test('[scenario 29] a real 409 preserves the draft and supports explicit conflict recovery', async ({ page }) => {
    await createSavedConnection(page, ['fake-report-model']);
    const mutation = await page.evaluate(async () => {
      const config = await fetch('/api/v1/system/config').then((response) => response.json());
      const response = await fetch('/api/v1/system/config', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          config_version: config.config_version,
          mask_token: config.mask_token,
          reload_now: true,
          items: [{ key: 'LLM_CUSTOM_MODELS', value: 'server-side-model' }],
        }),
      });
      return response.status;
    });
    expect(mutation).toBe(200);
    const conflictResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith('/api/v1/system/config') && response.request().method() === 'PUT',
    );
    await page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`).getByRole('button', { name: '编辑' }).click();
    await addManualModel(page, 'local-only-model');
    await page.getByRole('button', { name: '保存修改' }).click();
    const conflictResponse = await conflictResponsePromise;
    expect(conflictResponse.status()).toBe(409);
    const submittedItems = Object.fromEntries(
      (conflictResponse.request().postDataJSON() as { items: Array<{ key: string; value: string }> }).items
        .map((item) => [item.key, item.value]),
    );
    expect(submittedItems.LLM_CUSTOM_MODELS).toBe('fake-report-model,local-only-model');
    await expect(page.getByText('配置同时被其他会话修改')).toBeVisible({ timeout: 15_000 });
    const card = page.getByTestId(`connection-card-${CUSTOM_CONNECTION_ID}`);
    await expect(card).toContainText('fake-report-model');
    await expect(card).toContainText('local-only-model');
    await expect(card).toContainText('未保存');
    await page.getByRole('button', { name: '全部采用服务器值' }).click();
    await expect(page.getByText('配置同时被其他会话修改')).toHaveCount(0);
    await expect(card).toContainText('server-side-model');
    await expect(card).not.toContainText('local-only-model');
    await page.reload();
    await expect(card).toContainText('server-side-model');
    await expect(card).not.toContainText('local-only-model');
  });

  test('30 mobile modal is a bottom sheet and both themes remain usable', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openConnections(page);
    await selectTheme(page, '浅色');
    let dialog = await openAddDialog(page);
    let box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThanOrEqual(389);
    expect(Math.abs(box!.y + box!.height - 844)).toBeLessThanOrEqual(2);
    await capture(page, testInfo, 'connections-mobile-light-sheet');
    await dialog.getByRole('button', { name: '关闭', exact: true }).click();

    await selectTheme(page, '深色');
    dialog = await openAddDialog(page);
    box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThanOrEqual(389);
    expect(Math.abs(box!.y + box!.height - 844)).toBeLessThanOrEqual(2);
    await capture(page, testInfo, 'connections-mobile-dark-sheet');
  });
});
