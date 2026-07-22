// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Page } from '@playwright/test';
import { APP_ROUTE_PATHS, buildSettingsHref } from '../src/routing/routes';
import { encodeModelRef } from '../src/utils/modelRef';
import { loginAsE2eAdmin } from './auth-fixture';

const fakeProviderPort = Number(process.env.DSA_WEB_SMOKE_PROVIDER_PORT || 18101);
const fakeProviderBaseUrl = `http://127.0.0.1:${fakeProviderPort}/v1`;
const fakeProviderRootUrl = `http://127.0.0.1:${fakeProviderPort}`;
const SETTINGS_AUTOSAVE_DEBOUNCE_MS = 700;
const modelRef = (connection: string, model: string) => encodeModelRef(connection, `openai/${model}`);
const autosaveClockPages = new WeakSet<Page>();

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
  'LLM_CUSTOM_BASE_URL',
  'LLM_CUSTOM_API_KEY',
  'LLM_CUSTOM_API_KEYS',
  'LLM_CUSTOM_MODELS',
  'LLM_CUSTOM_ENABLED',
  'LLM_OPENAI_PROTOCOL',
  'LLM_OPENAI_PROVIDER',
  'LLM_OPENAI_BASE_URL',
  'LLM_OPENAI_API_KEY',
  'LLM_OPENAI_API_KEYS',
  'LLM_OPENAI_MODELS',
  'LLM_OPENAI_ENABLED',
  'LLM_OPENAI2_PROTOCOL',
  'LLM_OPENAI2_PROVIDER',
  'LLM_OPENAI2_BASE_URL',
  'LLM_OPENAI2_API_KEY',
  'LLM_OPENAI2_API_KEYS',
  'LLM_OPENAI2_MODELS',
  'LLM_OPENAI2_ENABLED',
  'LLM_PRIMARY_GATEWAY_PROTOCOL',
  'LLM_PRIMARY_GATEWAY_PROVIDER',
  'LLM_PRIMARY_GATEWAY_BASE_URL',
  'LLM_PRIMARY_GATEWAY_API_KEY',
  'LLM_PRIMARY_GATEWAY_API_KEYS',
  'LLM_PRIMARY_GATEWAY_MODELS',
  'LLM_PRIMARY_GATEWAY_ENABLED',
  'LLM_OLLAMA_PROTOCOL',
  'LLM_OLLAMA_PROVIDER',
  'LLM_OLLAMA_BASE_URL',
  'LLM_OLLAMA_API_KEY',
  'LLM_OLLAMA_API_KEYS',
  'LLM_OLLAMA_MODELS',
  'LLM_OLLAMA_ENABLED',
  'LITELLM_MODEL',
  'AGENT_LITELLM_MODEL',
  'VISION_MODEL',
  'LITELLM_FALLBACK_MODELS',
];

async function selectTheme(page: Page, theme: '浅色' | '深色') {
  let themeTrigger = page.getByRole('button', { name: '切换主题' }).first();
  if (!await themeTrigger.isVisible().catch(() => false)) {
    const profileTrigger = page.getByRole('button', { name: 'StockPulse', exact: true }).last();
    if (await profileTrigger.getAttribute('aria-expanded') !== 'true') {
      await profileTrigger.click();
    }
    themeTrigger = page.getByRole('button', { name: '切换主题' }).first();
  }
  await themeTrigger.click();
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

async function openSettings(page: Page) {
  await login(page);
  await page.goto(APP_ROUTE_PATHS.settings);
  await expect(page.getByRole('heading', { name: '系统设置' })).toBeVisible({ timeout: 15_000 });
}

async function openConnections(page: Page, reset = true) {
  await login(page);
  if (reset) {
    await resetModelConfig(page);
  }
  await page.goto(buildSettingsHref({ section: 'ai_models', view: 'connections' }));
  await expect(page.getByRole('heading', { name: '模型接入' })).toBeVisible({ timeout: 15_000 });
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

interface AutosaveExpectation {
  channels?: string;
  providers?: Record<string, string>;
  status?: number;
}

interface AutosaveResult {
  payload: { items: Array<{ key: string; value: string }> };
  refreshed?: { items: Array<{ key: string; value: string }> };
}

async function waitForAiAutosave(
  page: Page,
  trigger: () => Promise<void>,
  expectation: AutosaveExpectation = { channels: 'custom', providers: { custom: 'custom' } },
): Promise<AutosaveResult> {
  if (!autosaveClockPages.has(page)) {
    await page.clock.install();
    autosaveClockPages.add(page);
  }
  const expectedStatus = expectation.status ?? 200;
  const responsePromise = page.waitForResponse(
    (response) => response.url().endsWith('/api/v1/system/config') && response.request().method() === 'PUT',
  );
  const refreshPromise = expectedStatus === 200
    ? page.waitForResponse(
      (response) => response.url().includes('/api/v1/system/config?include_schema=true')
        && response.request().method() === 'GET',
    )
    : null;

  await trigger();
  await expect(page.getByText(/AI 模型: (等待自动保存|自动保存中…)/)).toBeVisible();
  await page.clock.fastForward(SETTINGS_AUTOSAVE_DEBOUNCE_MS + 1);

  const response = await responsePromise;
  expect(response.status()).toBe(expectedStatus);
  const payload = response.request().postDataJSON() as AutosaveResult['payload'];
  if (!refreshPromise) {
    await expect(page.getByText(/AI 模型: 保存冲突/)).toBeVisible();
    return { payload };
  }

  const refreshResponse = await refreshPromise;
  expect(refreshResponse.status()).toBe(200);
  const refreshed = await refreshResponse.json() as AutosaveResult['refreshed'];
  await expect(page.getByText(/AI 模型: 已自动保存/)).toBeVisible();

  if (expectation.channels !== undefined) {
    expect(refreshed?.items.find((item) => item.key === 'LLM_CHANNELS')?.value).toBe(expectation.channels);
  }
  for (const [connection, provider] of Object.entries(expectation.providers ?? {})) {
    const providerKey = `LLM_${connection.toUpperCase()}_PROVIDER`;
    expect(refreshed?.items.find((item) => item.key === providerKey)?.value).toBe(provider);
  }
  return { payload, refreshed };
}

async function configureCustomConnection(page: Page, selectedModels = ['fake-report-model']) {
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
  return waitForAiAutosave(page, async () => {
    await page.getByRole('button', { name: '添加到配置' }).click();
    await expect(dialog).toBeHidden();
  });
}

async function configureOpenAiConnection(page: Page, name: string, model: string) {
  const dialog = await openAddDialog(page);
  await chooseProvider(page, 'openai');
  await dialog.getByLabel('连接名称').fill(name);
  await dialog.getByLabel('API 密钥').fill('e2e-openai-key');
  await dialog.getByRole('button', { name: '使用自定义服务地址' }).click();
  await dialog.getByLabel('服务地址').fill(fakeProviderBaseUrl);
  await addManualModel(page, model);
  return waitForAiAutosave(page, async () => {
    await dialog.getByRole('button', { name: '添加到配置' }).click();
    await expect(dialog).toBeHidden();
  }, { channels: 'openai', providers: { openai: 'openai' } });
}

async function createSavedConnection(page: Page, selectedModels = ['fake-report-model', 'fake-agent-model', 'fake-vision-model']) {
  await openConnections(page, true);
  await configureCustomConnection(page, selectedModels);
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
    await page.goto(buildSettingsHref({ legacyCategory: 'ai_model', legacySub: 'providers' }));
    await expect(page.getByRole('heading', { name: '模型接入' })).toBeVisible();
    await expect.poll(() => page.url()).toContain('section=ai_models');
    expect(page.url()).toContain('view=connections');
    expect(page.url()).not.toContain('sub=providers');
  });

  test('03 Model Access has the concise title, description, and one primary action', async ({ page }) => {
    await openConnections(page);
    await selectTheme(page, '浅色');
    await expect(page.getByText('连接模型服务，并管理可用于报告、Agent 和视觉任务的模型。')).toBeVisible();
    await expect(page.getByRole('button', { name: /添加模型服务/ })).toHaveCount(1);
  });

  test('04 Model Access removes generation-backend diagnostics from the first screen', async ({ page }) => {
    await openConnections(page);
    const main = page.locator('main');
    await expect(main.getByText('生成后端状态')).toHaveCount(0);
    await expect(main.getByText('主后端')).toHaveCount(0);
    await expect(main.getByText('备用后端')).toHaveCount(0);
  });

  test('05 Model Access never lays credential fields out on the page', async ({ page }) => {
    await createSavedConnection(page);
    await expect(page.getByLabel('API 密钥')).toHaveCount(0);
    await expect(page.getByLabel('服务地址')).toHaveCount(0);
    await expect(page.getByTestId('connection-card-custom')).toContainText('fake-report-model');
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

  test('09 official providers hide protocol and default Base URL', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'openai');
    await expect(dialog.getByLabel('协议')).toHaveCount(0);
    await expect(dialog.getByLabel('服务地址')).toHaveCount(0);
    await expect(dialog.getByText('使用服务商官方地址')).toBeVisible();
    await expect(dialog.getByLabel('API 密钥')).toBeVisible();
  });

  test('09b a second OpenAI Connection persists the same explicit Provider identity', async ({ page }) => {
    await openConnections(page);
    await configureOpenAiConnection(page, 'openai', 'fake-report-model');

    const dialog = await openAddDialog(page);
    await dialog.getByLabel('选择模型服务商').click();
    const openAiOption = page.locator('[role="option"][data-value="openai"]');
    await expect(openAiOption).toContainText('已接入 1 条');
    await openAiOption.click();
    await dialog.getByRole('button', { name: '下一步' }).click();
    await dialog.getByLabel('连接名称').fill('openai2');
    await dialog.getByLabel('API 密钥').fill('e2e-openai-key-2');
    await dialog.getByRole('button', { name: '使用自定义服务地址' }).click();
    await dialog.getByLabel('服务地址').fill(fakeProviderBaseUrl);
    await addManualModel(page, 'fake-agent-model');
    await waitForAiAutosave(page, async () => {
      await dialog.getByRole('button', { name: '添加到配置' }).click();
      await expect(dialog).toBeHidden();
    }, {
      channels: 'openai,openai2',
      providers: { openai: 'openai', openai2: 'openai' },
    });
    const available = await page.evaluate(async () => (
      fetch('/api/v1/system/config/llm/available-models').then((response) => response.json())
    ));
    expect(available.models).toEqual(expect.arrayContaining([
      expect.objectContaining({
        route: 'openai/fake-report-model',
        model_ref: modelRef('openai', 'fake-report-model'),
        connection_id: 'openai',
        connection_name: 'openai',
        provider_id: 'openai',
        provider_label: 'OpenAI 官方',
      }),
      expect.objectContaining({
        route: 'openai/fake-agent-model',
        model_ref: modelRef('openai2', 'fake-agent-model'),
        connection_id: 'openai2',
        connection_name: 'openai2',
        provider_id: 'openai',
        provider_label: 'OpenAI 官方',
      }),
    ]));
  });

  test('09c renaming an OpenAI Connection preserves Provider identity and model metadata', async ({ page }) => {
    await openConnections(page);
    await configureOpenAiConnection(page, 'openai', 'fake-report-model');

    await page.getByTestId('connection-card-openai').getByRole('button', { name: '编辑' }).click();
    const dialog = page.getByRole('dialog', { name: '编辑模型服务' });
    await dialog.getByLabel('连接名称').fill('primary_gateway');
    await waitForAiAutosave(page, async () => {
      await dialog.getByRole('button', { name: '保存修改' }).click();
      await expect(dialog).toBeHidden();
    }, {
      channels: 'openai',
      providers: { openai: 'openai' },
    });
    await expect(page.getByTestId('connection-card-openai')).toContainText('primary_gateway');

    const available = await page.evaluate(async () => (
      fetch('/api/v1/system/config/llm/available-models').then((response) => response.json())
    ));
    expect(available.models).toContainEqual(expect.objectContaining({
      route: 'openai/fake-report-model',
      model_ref: modelRef('openai', 'fake-report-model'),
      connection_id: 'openai',
      connection_name: 'primary_gateway',
      provider_id: 'openai',
      provider_label: 'OpenAI 官方',
    }));
  });

  test('10 Ollama hides API key and can reveal an address override', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'ollama');
    await expect(dialog.getByLabel('API 密钥')).toHaveCount(0);
    await dialog.getByRole('button', { name: '使用自定义服务地址' }).click();
    await expect(dialog.getByLabel('服务地址')).toHaveValue('http://127.0.0.1:11434');
  });

  test('10b Ollama discovers through api/tags and tests with an empty API key', async ({ page, request }) => {
    await request.delete(`${fakeProviderRootUrl}/__requests`);
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'ollama');
    await expect(dialog.getByLabel('API 密钥')).toHaveCount(0);
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
    await expect(dialog.getByLabel('API 密钥')).toBeVisible();
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
    await dialog.getByLabel('API 密钥').fill('e2e-custom-key');
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
    await expect(dialog.getByLabel('API 密钥')).toHaveAttribute('placeholder', '本地服务可留空');
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

  test('17 Add to configuration schedules the AI group autosave without a global Save', async ({ page }) => {
    await openConnections(page);
    let saves = 0;
    page.on('request', (request) => {
      if (request.url().endsWith('/api/v1/system/config') && request.method() === 'PUT') saves += 1;
    });
    await configureCustomConnection(page);
    expect(saves).toBe(1);
    await expect(page.getByRole('button', { name: /保存配置/ })).toHaveCount(0);
    await expect(page.getByTestId('connection-card-custom')).toContainText('fake-report-model');
  });

  test('18 autosave performs one atomic transaction and persists the card', async ({ page }) => {
    await openConnections(page);
    let saves = 0;
    page.on('request', (request) => {
      if (request.url().endsWith('/api/v1/system/config') && request.method() === 'PUT') saves += 1;
    });
    await configureCustomConnection(page);
    expect(saves).toBe(1);
    await page.reload();
    await expect(page.getByTestId('connection-card-custom')).toContainText('fake-report-model');
  });

  test('18b a Connection card shows Provider identity, enablement, and independent test status', async ({ page }) => {
    await createSavedConnection(page, ['fake-report-model']);
    const card = page.getByTestId('connection-card-custom');
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
    await page.getByTestId('connection-card-custom').getByRole('button', { name: '编辑' }).click();
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
    await expect(page.getByTestId('connection-card-custom')).toBeVisible();
    await waitForAiAutosave(page, async () => {
      await dialog.getByRole('button', { name: '删除连接' }).click();
    }, { channels: '', providers: {} });
    await expect(page.getByTestId('connection-card-custom')).toHaveCount(0);
  });

  test('21b deleting a referenced Connection is blocked by both the API and the page workflow', async ({ page }) => {
    await createSavedConnection(page, ['fake-report-model', 'fake-agent-model']);
    await page.getByRole('tab', { name: '任务路由' }).click();
    const reportModelRef = modelRef('custom', 'fake-report-model');
    await waitForAiAutosave(page, () => selectStrictModel(page, '主要模型', reportModelRef));

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
    expect(rejected.channels).toBe('custom');
    expect(rejected.body.params.issues).toEqual(expect.arrayContaining([
      expect.objectContaining({
        code: 'model_in_use',
        details: expect.objectContaining({
          model_ref: reportModelRef,
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
    await expect(page.getByTestId('connection-card-custom')).toBeVisible();
    await dialog.getByRole('button', { name: '前往任务路由替换' }).click();
    await expect(page.getByRole('heading', { name: '任务路由' })).toBeVisible();
    await expect(page.getByRole('button', { name: '主要模型', exact: true })).toHaveAttribute(
      'data-value',
      reportModelRef,
    );
  });

  test('22 task routing empty state links to model access', async ({ page }) => {
    await openConnections(page);
    await page.getByRole('tab', { name: '任务路由' }).click();
    await expect(page.getByText('还没有可用模型')).toBeVisible();
    await page.getByRole('button', { name: '前往模型接入' }).click();
    await expect(page.getByRole('heading', { name: '模型接入' })).toBeVisible();
  });

  test('22b task routing round-trip preserves source, Back/Forward, and refreshes models after save', async ({ page }) => {
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

    await configureCustomConnection(page, ['fake-report-model']);
    await page.getByRole('button', { name: '返回任务路由' }).click();
    await expect(page).toHaveURL(/section=ai_models&view=task_routing/);
    await expect(page).not.toHaveURL(/from=task_routing/);
    await page.getByRole('button', { name: '主要模型', exact: true }).click();
    await expect(page.locator(`[role="option"][data-value="${modelRef('custom', 'fake-report-model')}"]`)).toBeVisible();
  });

  test('23 available-model API errors are distinct from empty state and retryable', async ({ page }) => {
    await login(page);
    await resetModelConfig(page);
    await page.route('**/api/v1/system/config/llm/available-models', (route) => route.fulfill({ status: 500, body: '{}' }));
    await page.goto(buildSettingsHref({ section: 'ai_models', view: 'task_routing' }));
    await expect(page.getByText(/可用模型加载失败/)).toBeVisible();
    await expect(page.getByRole('button', { name: /重试|重新加载/ })).toBeVisible();
    await expect(page.getByText('还没有可用模型')).toHaveCount(0);
  });

  test('24 task models use strict SearchableSelect controls', async ({ page }) => {
    await createSavedConnection(page);
    await page.getByRole('tab', { name: '任务路由' }).click();
    const reportModelRef = modelRef('custom', 'fake-report-model');
    for (const label of ['主要模型', 'Agent 主要模型', 'Vision 模型']) {
      const trigger = page.getByRole('button', { name: label, exact: true });
      await expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');
      await trigger.click();
      await expect(page.locator(`[role="option"][data-value="${reportModelRef}"]`)).toBeVisible();
      await page.getByRole('combobox', { name: new RegExp(label) }).press('Escape');
    }
    await expect(page.locator('input[aria-label="主要模型"]')).toHaveCount(0);
  });

  test('24b Report, Agent, and Vision selections persist exact Connection model refs in one autosave', async ({ page }) => {
    await createSavedConnection(page);
    await page.getByRole('tab', { name: '任务路由' }).click();
    const reportModelRef = modelRef('custom', 'fake-report-model');
    const agentModelRef = modelRef('custom', 'fake-agent-model');
    const visionModelRef = modelRef('custom', 'fake-vision-model');
    const { payload, refreshed } = await waitForAiAutosave(page, async () => {
      await selectStrictModel(page, '主要模型', reportModelRef);
      await selectStrictModel(page, 'Agent 主要模型', agentModelRef);
      await selectStrictModel(page, 'Vision 模型', visionModelRef);
    });
    const submitted = Object.fromEntries(payload.items.map((item) => [item.key, item.value]));
    expect(submitted).toMatchObject({
      LITELLM_MODEL: reportModelRef,
      AGENT_LITELLM_MODEL: agentModelRef,
      VISION_MODEL: visionModelRef,
    });
    const persisted = Object.fromEntries(
      refreshed.items.map((item: { key: string; value: string }) => [item.key, item.value]),
    );
    expect(persisted).toMatchObject({
      LITELLM_MODEL: reportModelRef,
      AGENT_LITELLM_MODEL: agentModelRef,
      VISION_MODEL: visionModelRef,
    });
  });

  test('25 selected task routes survive Available Models becoming stale', async ({ page }) => {
    await createSavedConnection(page);
    await page.getByRole('tab', { name: '任务路由' }).click();
    const reportModelRef = modelRef('custom', 'fake-report-model');
    await waitForAiAutosave(page, () => selectStrictModel(page, '主要模型', reportModelRef));
    await page.route('**/api/v1/system/config/llm/available-models', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ models: [] }),
    }));
    await page.reload();
    await expect(page.getByText(/当前配置不可用.*fake-report-model/)).toBeVisible();
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

  test('26b referenced model deletion lists every task and replaces all references in one autosave', async ({ page }) => {
    await createSavedConnection(page);
    const reportModelRef = modelRef('custom', 'fake-report-model');
    const agentModelRef = modelRef('custom', 'fake-agent-model');
    await waitForAiAutosave(page, async () => {
      await page.getByRole('tab', { name: '可靠性' }).click();
      await page.getByRole('button', { name: '选择备用模型' }).click();
      await page.getByRole('checkbox', { name: 'fake-report-model' }).check();
      await page.getByLabel('搜索模型').press('Escape');
      await page.getByRole('tab', { name: '任务路由' }).click();
      await selectStrictModel(page, '主要模型', reportModelRef);
      await selectStrictModel(page, 'Agent 主要模型', reportModelRef);
      await selectStrictModel(page, 'Vision 模型', reportModelRef);
    });

    await page.getByRole('tab', { name: '模型接入' }).click();
    await page.getByRole('button', { name: '管理模型 e2e' }).click();
    const dialog = page.getByRole('dialog', { name: '编辑模型服务' });
    await dialog.getByRole('button', { name: '移除模型 fake-report-model' }).click();
    const conflict = dialog.getByRole('status').filter({ hasText: '无法直接删除模型' });
    await expect(dialog.getByText('无法直接删除模型')).toBeVisible();
    for (const task of ['报告', 'Agent', 'Vision', '备用']) {
      await expect(conflict.getByText(task, { exact: true })).toBeVisible();
    }
    await expect(dialog.getByRole('button', { name: '移除模型 fake-report-model' })).toBeVisible();
    await dialog.getByRole('button', { name: '替代模型' }).click();
    await page.locator(`[role="option"][data-value="${agentModelRef}"]`).click();
    await dialog.getByRole('button', { name: '替换引用并删除' }).click();
    await expect(dialog.getByText('无法直接删除模型')).toHaveCount(0);
    await expect(dialog.getByRole('button', { name: '移除模型 fake-report-model' })).toHaveCount(0);
    const { payload } = await waitForAiAutosave(page, async () => {
      await dialog.getByRole('button', { name: '保存修改' }).click();
      await expect(dialog).toBeHidden();
    });
    const submitted = Object.fromEntries(payload.items.map((item) => [item.key, item.value]));
    expect(submitted.LLM_CUSTOM_MODELS).toBe('fake-agent-model,fake-vision-model');
    expect(submitted).toMatchObject({
      LITELLM_MODEL: agentModelRef,
      AGENT_LITELLM_MODEL: agentModelRef,
      VISION_MODEL: agentModelRef,
      LITELLM_FALLBACK_MODELS: agentModelRef,
    });
  });

  test('26c Reset current group cancels its scheduled autosave', async ({ page }) => {
    await createSavedConnection(page);
    let putCount = 0;
    page.on('request', (request) => {
      if (request.url().endsWith('/api/v1/system/config') && request.method() === 'PUT') putCount += 1;
    });
    await page.getByRole('tab', { name: '任务路由' }).click();
    await selectStrictModel(page, '主要模型', modelRef('custom', 'fake-report-model'));
    await expect(page.getByText(/AI 模型: 等待自动保存/)).toBeVisible();
    await page.getByRole('button', { name: '重置当前分组' }).click();
    const resetDialog = page.getByRole('dialog', { name: '放弃未保存的修改？' });
    await resetDialog.getByRole('button', { name: '放弃修改' }).click();
    await expect(page.getByRole('button', { name: '主要模型', exact: true })).toHaveAttribute('data-value', '');
    await expect(page.getByText(/AI 模型: 等待自动保存/)).toHaveCount(0);
    await page.clock.fastForward(SETTINGS_AUTOSAVE_DEBOUNCE_MS + 1);
    expect(putCount).toBe(0);
  });

  test('27 provider catalog failure is compact and keeps a renamed official Provider identity', async ({ page }) => {
    await openConnections(page);
    await configureOpenAiConnection(page, 'primary_gateway', 'fake-report-model');
    await page.route('**/api/v1/system/config/llm/providers', (route) => route.fulfill({ status: 500, body: '{}' }));
    await page.reload();
    const card = page.getByTestId('connection-card-openai');
    await expect(card).toBeVisible();
    await expect(card).toContainText('openai');
    await expect(card).not.toContainText('自定义服务');
    await expect(card).not.toContainText('草稿 · 未完成');
    await expect(card).not.toContainText('缺少服务地址');
    await expect(page.getByText('模型服务列表加载失败')).toBeVisible();
    await expect(page.getByRole('button', { name: '重试' })).toBeVisible();
  });

  test('28 developer diagnostics is a dedicated uncollapsed Advanced tab', async ({ page }) => {
    await openSettings(page);
    // Backend Status keeps the banner/status panels on the default tab.
    await page.goto(buildSettingsHref({ section: 'advanced', view: 'raw_config' }));
    await expect(page.getByTestId('generation-backend-status-panel')).toBeVisible();
    // Developer fields moved to their own tab and render without a collapsible.
    await page.getByRole('tab', { name: '开发者诊断' }).click();
    await expect(page.getByRole('heading', { name: '开发者诊断' })).toBeVisible();
    await expect(page.locator('details').filter({ hasText: '开发者诊断' })).toHaveCount(0);
  });

  test('29 a real 409 keeps the local draft and surfaces conflict UI', async ({ page }) => {
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
    await page.getByTestId('connection-card-custom').getByRole('button', { name: '编辑' }).click();
    const dialog = page.getByRole('dialog', { name: '编辑模型服务' });
    await addManualModel(page, 'local-only-model');
    await waitForAiAutosave(page, async () => {
      await dialog.getByRole('button', { name: '保存修改' }).click();
      await expect(dialog).toBeHidden();
    }, { status: 409 });
    await expect(page.getByText(/配置版本冲突|保存冲突/).first()).toBeVisible();
    await expect(page.getByTestId('connection-card-custom')).toContainText('local-only-model');
  });

  test('30 mobile modal is a bottom sheet and both themes remain usable', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openConnections(page);
    await selectTheme(page, '浅色');
    let dialog = await openAddDialog(page);
    let box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThanOrEqual(389);
    expect(Math.abs(box!.y + box!.height - 844)).toBeLessThanOrEqual(2);
    await dialog.getByRole('button', { name: '关闭', exact: true }).click();

    await selectTheme(page, '深色');
    dialog = await openAddDialog(page);
    box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThanOrEqual(389);
    expect(Math.abs(box!.y + box!.height - 844)).toBeLessThanOrEqual(2);
  });
});
