import { expect, test, type Page, type TestInfo } from '@playwright/test';

const smokePassword = process.env.DSA_WEB_SMOKE_PASSWORD || 'dsa-e2e-smoke';
const fakeProviderPort = Number(process.env.DSA_WEB_SMOKE_PROVIDER_PORT || 18101);
const fakeProviderBaseUrl = `http://127.0.0.1:${fakeProviderPort}/v1`;

const MODEL_KEYS_TO_RESET = [
  'LLM_CONFIG_MODE',
  'LLM_CHANNELS',
  'LLM_E2E_PROTOCOL',
  'LLM_E2E_BASE_URL',
  'LLM_E2E_API_KEY',
  'LLM_E2E_API_KEYS',
  'LLM_E2E_MODELS',
  'LLM_E2E_ENABLED',
  'LLM_OPENAI_PROTOCOL',
  'LLM_OPENAI_BASE_URL',
  'LLM_OPENAI_API_KEY',
  'LLM_OPENAI_API_KEYS',
  'LLM_OPENAI_MODELS',
  'LLM_OPENAI_ENABLED',
  'LLM_OLLAMA_PROTOCOL',
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
  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded');
  const settingsLink = page.getByRole('link', { name: '设置' });
  if (
    page.url().endsWith('/')
    || await settingsLink.isVisible({ timeout: 2_000 }).catch(() => false)
  ) {
    return;
  }

  const password = page.locator('#password');
  // Auth-disabled developer builds redirect /login to the workspace without a
  // password field. The isolated CI env enables auth, so this branch remains a
  // real first-login flow there while local runs stay independent of user state.
  if (!await password.isVisible({ timeout: 3_000 }).catch(() => false)) {
    return;
  }
  await password.fill(smokePassword);
  const confirmation = page.locator('#passwordConfirm');
  if (await confirmation.isVisible({ timeout: 1_000 }).catch(() => false)) {
    await confirmation.fill(smokePassword);
  }
  await Promise.all([
    page.waitForResponse(
      (response) => response.url().includes('/api/v1/auth/login') && response.status() === 200,
      { timeout: 20_000 },
    ),
    page.getByRole('button', { name: /授权进入工作台|完成设置并登录/ }).click(),
  ]);
  await page.waitForURL('/', { timeout: 20_000 });
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
  await page.goto('/settings');
  await expect(page.getByRole('heading', { name: '系统设置' })).toBeVisible({ timeout: 15_000 });
}

async function openConnections(page: Page, reset = true) {
  await login(page);
  if (reset) {
    await resetModelConfig(page);
  }
  await page.goto('/settings?section=ai_models&view=connections');
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
    return;
  }
  await page.locator(`[role="option"][data-value="${id}"]`).click();
}

async function chooseProviderBySearch(page: Page, query: string, id: string) {
  await page.getByLabel('选择模型服务商').click();
  await page.getByRole('combobox', { name: '选择模型服务商 搜索' }).fill(query);
  await page.locator(`[role="option"][data-value="${id}"]`).click();
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
  for (const model of selectedModels) {
    await page.getByRole('checkbox', { name: model }).check();
  }
  await page.getByRole('button', { name: '添加到配置' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId('connection-card-e2e')).toContainText('未保存');
}

async function saveDraft(page: Page) {
  const responsePromise = page.waitForResponse(
    (response) => response.url().endsWith('/api/v1/system/config') && response.request().method() === 'PUT',
    { timeout: 20_000 },
  );
  const refreshPromise = page.waitForResponse(
    (response) => response.url().includes('/api/v1/system/config?include_schema=true') && response.request().method() === 'GET',
    { timeout: 20_000 },
  );
  await page.getByRole('button', { name: /保存配置/ }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const refreshResponse = await refreshPromise;
  expect(refreshResponse.status()).toBe(200);
  const refreshed = await refreshResponse.json();
  expect(refreshed.items.find((item: { key: string }) => item.key === 'LLM_CHANNELS')?.value).toBe('e2e');
  if (await page.getByTestId('connection-card-e2e').count()) {
    await expect(page.getByTestId('connection-card-e2e')).not.toContainText('未保存', { timeout: 15_000 });
  }
}

async function createSavedConnection(page: Page, selectedModels = ['fake-report-model', 'fake-agent-model', 'fake-vision-model']) {
  await openConnections(page, true);
  await configureCustomDraft(page, selectedModels);
  await saveDraft(page);
}

async function selectStrictModel(page: Page, label: string, route: string) {
  await page.getByRole('button', { name: label, exact: true }).click();
  await page.locator(`[role="option"][data-value="${route}"]`).click();
}

test.describe('model access product convergence', () => {
  test.use({ locale: 'zh-CN' });

  test('01 AI & Models exposes exactly four product views', async ({ page }) => {
    await openConnections(page);
    for (const label of ['总览', '连接', '任务路由', '可靠性']) {
      await expect(page.getByRole('tab', { name: label })).toBeVisible();
    }
    await expect(page.getByRole('tab', { name: '高级' })).toHaveCount(0);
  });

  test('02 legacy provider URLs replace-redirect to Connections', async ({ page }) => {
    await login(page);
    await page.goto('/settings?category=ai_model&sub=providers');
    await expect(page.getByRole('heading', { name: '模型接入' })).toBeVisible();
    await expect.poll(() => page.url()).toContain('section=ai_models');
    expect(page.url()).toContain('view=connections');
    expect(page.url()).not.toContain('sub=providers');
  });

  test('03 Connections has the concise title, description, and one primary action', async ({ page }, testInfo) => {
    await openConnections(page);
    await selectTheme(page, '浅色');
    await expect(page.getByText('连接模型服务，并管理可用于报告、Agent 和视觉任务的模型。')).toBeVisible();
    await expect(page.getByRole('button', { name: /添加模型服务/ })).toHaveCount(2);
    await capture(page, testInfo, 'connections-empty-light');
  });

  test('04 Connections removes generation-backend diagnostics from the first screen', async ({ page }) => {
    await openConnections(page);
    const main = page.locator('main');
    await expect(main.getByText('生成后端状态')).toHaveCount(0);
    await expect(main.getByText('主后端')).toHaveCount(0);
    await expect(main.getByText('备用后端')).toHaveCount(0);
  });

  test('05 Connections never lays credential fields out on the page', async ({ page }) => {
    await createSavedConnection(page);
    await expect(page.getByLabel('API 密钥')).toHaveCount(0);
    await expect(page.getByLabel('服务地址')).toHaveCount(0);
    await expect(page.getByTestId('connection-card-e2e')).toContainText('fake-report-model');
  });

  test('06 normal AI views contain no raw config keys or legacy terminology', async ({ page }) => {
    await openConnections(page);
    for (const label of ['总览', '连接', '任务路由', '可靠性']) {
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
    await expect(page.locator('[role="option"][data-value="custom"]')).toContainText('自定义服务');
    await expect(dialog).toBeVisible();
  });

  test('08 provider picker is searchable by provider metadata', async ({ page }) => {
    await openConnections(page);
    await openAddDialog(page);
    await page.getByLabel('选择模型服务商').click();
    await page.getByRole('combobox', { name: '选择模型服务商 搜索' }).fill('local-runtime');
    await expect(page.locator('[role="option"][data-value="ollama"]')).toBeVisible();
    await expect(page.locator('[role="option"][data-value="openai"]')).toHaveCount(0);
  });

  test('09 official providers hide protocol and default Base URL', async ({ page }, testInfo) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'openai');
    await expect(dialog.getByLabel('协议')).toHaveCount(0);
    await expect(dialog.getByLabel('服务地址')).toHaveCount(0);
    await expect(dialog.getByText('使用服务商官方地址')).toBeVisible();
    await expect(dialog.getByLabel('API 密钥')).toBeVisible();
    await capture(page, testInfo, 'add-openai-modal');
  });

  test('10 Ollama hides API key and can reveal an address override', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'ollama');
    await expect(dialog.getByLabel('API 密钥')).toHaveCount(0);
    await dialog.getByRole('button', { name: '使用自定义服务地址' }).click();
    await expect(dialog.getByLabel('服务地址')).toHaveValue('http://127.0.0.1:11434');
  });

  test('11 custom service exposes enum protocol, address, and key controls', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'custom');
    await expect(dialog.getByLabel('协议')).toHaveAttribute('role', 'combobox');
    await expect(dialog.getByLabel('服务地址')).toBeVisible();
    await expect(dialog.getByLabel('API 密钥')).toBeVisible();
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
    await expect(dialog.getByRole('button', { name: '添加到配置' })).toBeDisabled();
  });

  test('14 discovered models support search and explicit multi-selection', async ({ page }) => {
    await openConnections(page);
    const dialog = await openAddDialog(page);
    await chooseProvider(page, 'custom');
    await dialog.getByLabel('服务地址').fill(fakeProviderBaseUrl);
    await dialog.getByRole('button', { name: '获取模型' }).click();
    await expect(dialog.getByText('已选 0 / 3')).toBeVisible({ timeout: 20_000 });
    await dialog.getByLabel('搜索模型').fill('vision');
    await expect(dialog.getByRole('checkbox', { name: 'fake-vision-model' })).toBeVisible();
    await expect(dialog.getByRole('checkbox', { name: 'fake-report-model' })).toHaveCount(0);
    await dialog.getByRole('checkbox', { name: 'fake-vision-model' }).check();
    await expect(dialog.getByRole('button', { name: '移除模型 fake-vision-model' })).toBeVisible();
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

  test('17 Add to configuration changes only the unified page draft', async ({ page }) => {
    await openConnections(page);
    let saves = 0;
    page.on('request', (request) => {
      if (request.url().endsWith('/api/v1/system/config') && request.method() === 'PUT') saves += 1;
    });
    await configureCustomDraft(page);
    expect(saves).toBe(0);
    await expect(page.getByTestId('connection-card-e2e')).toContainText('未保存');
  });

  test('18 the page Save performs one atomic transaction and persists the card', async ({ page }) => {
    await openConnections(page);
    await configureCustomDraft(page);
    let saves = 0;
    page.on('request', (request) => {
      if (request.url().endsWith('/api/v1/system/config') && request.method() === 'PUT') saves += 1;
    });
    await saveDraft(page);
    expect(saves).toBe(1);
    await page.reload();
    await expect(page.getByTestId('connection-card-e2e')).toContainText('fake-report-model');
  });

  test('19 Edit reuses the connection modal and keeps the page compact', async ({ page }) => {
    await createSavedConnection(page);
    await page.getByTestId('connection-card-e2e').getByRole('button', { name: '编辑' }).click();
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
    await expect(page.getByTestId('connection-card-e2e')).toBeVisible();
    await dialog.getByRole('button', { name: '删除连接' }).click();
    await expect(page.getByTestId('connection-card-e2e')).toHaveCount(0);
  });

  test('22 task routing empty state links to model access', async ({ page }) => {
    await openConnections(page);
    await page.getByRole('tab', { name: '任务路由' }).click();
    await expect(page.getByText('还没有可用模型')).toBeVisible();
    await page.getByRole('button', { name: '前往模型接入' }).click();
    await expect(page.getByRole('heading', { name: '模型接入' })).toBeVisible();
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
      await expect(page.locator('[role="option"][data-value="openai/fake-report-model"]')).toBeVisible();
      await page.getByRole('combobox', { name: new RegExp(`${label}.*搜索`) }).press('Escape');
    }
    await expect(page.locator('input[aria-label="主要模型"]')).toHaveCount(0);
  });

  test('25 selected task routes survive Available Models becoming stale', async ({ page }) => {
    await createSavedConnection(page);
    await page.getByRole('tab', { name: '任务路由' }).click();
    await selectStrictModel(page, '主要模型', 'openai/fake-report-model');
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
    await page.getByLabel('添加备用模型').click();
    await page.locator('[role="option"][data-value="openai/fake-agent-model"]').click();
    await page.getByLabel('添加备用模型').click();
    await page.locator('[role="option"][data-value="openai/fake-vision-model"]').click();
    await expect(page.getByRole('button', { name: '上移 fake-vision-model' })).toBeEnabled();
    await page.getByRole('button', { name: '上移 fake-vision-model' }).click();
    await expect(page.getByRole('button', { name: '上移 fake-vision-model' })).toBeDisabled();
    await page.getByLabel('添加备用模型').click();
    await expect(page.locator('[role="option"][data-value="openai/fake-vision-model"]')).toHaveCount(0);
  });

  test('27 provider catalog failure is compact and existing cards remain visible', async ({ page }) => {
    await createSavedConnection(page);
    await page.route('**/api/v1/system/config/llm/providers', (route) => route.fulfill({ status: 500, body: '{}' }));
    await page.reload();
    await expect(page.getByTestId('connection-card-e2e')).toBeVisible();
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

  test('29 a real 409 keeps the local draft and surfaces conflict UI', async ({ page }) => {
    await createSavedConnection(page, ['fake-report-model']);
    await page.getByTestId('connection-card-e2e').getByRole('button', { name: '编辑' }).click();
    await addManualModel(page, 'local-only-model');
    await page.getByRole('button', { name: '保存修改' }).click();
    await expect(page.getByTestId('connection-card-e2e')).toContainText('未保存');
    const mutation = await page.evaluate(async () => {
      const config = await fetch('/api/v1/system/config').then((response) => response.json());
      const response = await fetch('/api/v1/system/config', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          config_version: config.config_version,
          mask_token: config.mask_token,
          reload_now: true,
          items: [{ key: 'LLM_E2E_MODELS', value: 'server-side-model' }],
        }),
      });
      return response.status;
    });
    expect(mutation).toBe(200);
    const conflictResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith('/api/v1/system/config') && response.request().method() === 'PUT',
    );
    await page.getByRole('button', { name: /保存配置/ }).click();
    expect((await conflictResponsePromise).status()).toBe(409);
    await expect(page.getByText(/配置版本冲突/)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('connection-card-e2e')).toContainText('未保存');
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
    await page.getByRole('button', { name: '关闭抽屉' }).click();

    await selectTheme(page, '深色');
    dialog = await openAddDialog(page);
    box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThanOrEqual(389);
    expect(Math.abs(box!.y + box!.height - 844)).toBeLessThanOrEqual(2);
    await capture(page, testInfo, 'connections-mobile-dark-sheet');
  });
});
