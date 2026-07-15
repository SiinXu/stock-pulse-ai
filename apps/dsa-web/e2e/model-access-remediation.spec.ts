import { expect, test, type Page, type TestInfo } from '@playwright/test';

/**
 * Remediation E2E: model-access UX on the real app against a real backend
 * started without any LLM_* configuration ("plain path"). Requires
 * DSA_WEB_SMOKE_PASSWORD (same contract as smoke.spec.ts).
 */

const smokePassword = process.env.DSA_WEB_SMOKE_PASSWORD;

if (!smokePassword) {
  test.skip(true, 'Set DSA_WEB_SMOKE_PASSWORD to run authenticated remediation tests.');
}

const LEGACY_TERMS = ['模型供应商', '快速添加渠道', '渠道管理', '渠道列表', '添加渠道'];
const RAW_KEY_PATTERNS = [/LLM_CHANNELS/, /LLM_[A-Z0-9_]+_API_KEY/, /LITELLM_MODEL/];

async function capture(page: Page, testInfo: TestInfo, name: string) {
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({ path, fullPage: true });
  await testInfo.attach(name, { path, contentType: 'image/png' });
}

async function login(page: Page) {
  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded');

  const passwordInput = page.locator('#password');
  const submitButton = page.getByRole('button', { name: /授权进入工作台|完成设置并登录/ });
  const homeLink = page.getByRole('link', { name: '首页' });

  const isAlreadyAuthenticated =
    page.url().endsWith('/') ||
    (await homeLink.isVisible({ timeout: 2_000 }).catch(() => false));
  if (isAlreadyAuthenticated) {
    return;
  }

  await expect(passwordInput).toBeVisible({ timeout: 10_000 });
  await passwordInput.fill(smokePassword!);
  const confirmInput = page.locator('#passwordConfirm');
  if (await confirmInput.isVisible({ timeout: 1_000 }).catch(() => false)) {
    await confirmInput.fill(smokePassword!);
  }
  await Promise.all([
    page.waitForResponse(
      (response) => response.url().includes('/api/v1/auth/login') && response.status() === 200,
      { timeout: 15_000 },
    ),
    submitButton.click(),
  ]);
  await page.waitForURL('/', { timeout: 15_000 });
  await page.waitForLoadState('domcontentloaded');
}

async function openSettings(page: Page) {
  await login(page);
  await page.getByRole('link', { name: '设置' }).click();
  await page.waitForLoadState('domcontentloaded');
  await expect(page.getByRole('heading', { name: '系统设置' })).toBeVisible({ timeout: 15_000 });
}

async function openAiSection(page: Page) {
  await openSettings(page);
  await page.getByRole('button', { name: 'AI 与模型' }).click();
  await expect(page.getByRole('tab', { name: '连接' })).toBeVisible({ timeout: 10_000 });
}

/**
 * On the connections view: pick a provider in the catalog Select, then click
 * the "+ 添加模型服务" button. The new channel row auto-expands.
 */
async function addModelService(page: Page, providerLabel: RegExp) {
  const providerSelect = page
    .getByRole('combobox')
    .filter({ hasText: /选择服务商|AIHubmix|官方|（本地）|（聚合平台）/ })
    .first();
  await expect(providerSelect).toBeVisible({ timeout: 10_000 });
  // The listbox opens downward with a fixed position; park the trigger near the
  // top of the viewport so deep options (e.g. Ollama) stay clickable.
  await providerSelect.evaluate((element) => element.scrollIntoView({ block: 'start' }));
  await providerSelect.click();
  const option = page.getByRole('option', { name: providerLabel }).first();
  await expect(option).toBeVisible({ timeout: 5_000 });
  await option.scrollIntoViewIfNeeded();
  await option.click();
  await page.getByRole('button', { name: '+ 添加模型服务' }).click();
  await page.waitForTimeout(400);
}

test.describe('model access remediation', () => {
  test.use({ locale: 'zh-CN' });

  test('scenario 1: AI & Models exposes exactly overview/connections/task-routing/reliability views', async ({ page }, testInfo) => {
    await openAiSection(page);

    for (const label of ['总览', '连接', '任务路由', '可靠性']) {
      await expect(page.getByRole('tab', { name: label })).toBeVisible();
    }
    await expect(page.getByRole('tab', { name: '高级' })).toHaveCount(0);
    await capture(page, testInfo, 'remediation-ai-views');
  });

  test('scenario 2: connections view is the single model-access entry without legacy terms', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '连接' }).click();
    await expect(page.getByRole('heading', { name: '模型接入' })).toBeVisible({ timeout: 10_000 });

    const content = await page.locator('main, body').first().innerText();
    for (const term of LEGACY_TERMS) {
      expect(content, `page should not contain legacy term ${term}`).not.toContain(term);
    }
    await capture(page, testInfo, 'remediation-connections-entry');
  });

  test('scenario 3: plain path renders no raw LLM_* keys across AI views', async ({ page }, testInfo) => {
    await openAiSection(page);

    for (const label of ['总览', '连接', '任务路由', '可靠性']) {
      await page.getByRole('tab', { name: label }).click();
      await page.waitForTimeout(400);
      const content = await page.locator('main, body').first().innerText();
      for (const pattern of RAW_KEY_PATTERNS) {
        expect(content, `${label} view should not expose ${pattern}`).not.toMatch(pattern);
      }
    }
    await capture(page, testInfo, 'remediation-no-raw-llm-keys');
  });

  test('scenario 4: add model service lists providers from the backend catalog', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '连接' }).click();

    const providerSelect = page
      .getByRole('combobox')
      .filter({ hasText: /选择服务商|AIHubmix|官方|（本地）|（聚合平台）/ })
      .first();
    await expect(providerSelect).toBeVisible({ timeout: 10_000 });
    await providerSelect.click();

    const listbox = page.getByRole('listbox');
    await expect(listbox).toBeVisible({ timeout: 5_000 });
    for (const provider of [/DeepSeek/, /OpenAI/, /Ollama/]) {
      await expect(
        listbox.getByRole('option', { name: provider }).first(),
        `provider catalog should list ${provider}`,
      ).toBeVisible();
    }
    await capture(page, testInfo, 'remediation-provider-catalog');
  });

  test('scenario 5: Ollama connection marks the API key as optional', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '连接' }).click();

    await addModelService(page, /Ollama/);

    await expect(
      page.getByPlaceholder('本地 Ollama 可留空').first(),
    ).toBeVisible({ timeout: 5_000 });
    await capture(page, testInfo, 'remediation-ollama-optional-key');
  });

  test('scenario 6: connection form uses value examples and new field labels', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '连接' }).click();

    await addModelService(page, /DeepSeek/);

    const content = await page.locator('main, body').first().innerText();
    expect(content).toContain('服务地址');
    expect(content).toContain('API 密钥');
    // Value example surfaces as the base-URL placeholder (a plain URL).
    await expect(page.getByPlaceholder(/^https?:\/\//).first()).toBeVisible({ timeout: 5_000 });
    // Examples are plain values, not KEY=value env lines.
    expect(content).not.toMatch(/LLM_[A-Z0-9_]+_BASE_URL=/);
    expect(content).not.toMatch(/LLM_[A-Z0-9_]+_API_KEY=/);
    await capture(page, testInfo, 'remediation-connection-form-labels');
  });

  test('scenario 7: a new connection starts with no prefilled sample models', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '连接' }).click();

    await addModelService(page, /DeepSeek/);

    await expect(
      page.getByText(/尚未添加模型|尚未添加可用模型/).first(),
    ).toBeVisible({ timeout: 5_000 });
    await capture(page, testInfo, 'remediation-no-prefilled-models');
  });

  test('scenario 8: manual model entry adds tokens and splits pasted comma lists', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '连接' }).click();

    await addModelService(page, /DeepSeek/);

    const modelInput = page.getByPlaceholder(/输入模型|模型 ID/).first();
    await expect(modelInput).toBeVisible({ timeout: 5_000 });

    await modelInput.fill('model-alpha');
    await modelInput.press('Enter');
    await expect(page.getByText('model-alpha', { exact: true }).first()).toBeVisible();

    await modelInput.fill('model-beta,model-gamma model-alpha');
    await modelInput.press('Enter');
    await expect(page.getByText('model-beta', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('model-gamma', { exact: true }).first()).toBeVisible();
    // Dedupe: model-alpha appears exactly once as a removable token chip.
    await expect(page.getByRole('button', { name: '移除模型 model-alpha' })).toHaveCount(1);
    await capture(page, testInfo, 'remediation-token-model-entry');
  });

  test('scenario 9: task routing empty state links back to connections', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '任务路由' }).click();

    await expect(page.getByText(/尚无可用模型|还没有可用模型/).first()).toBeVisible({ timeout: 10_000 });
    const addButton = page.getByRole('button', { name: '添加模型服务' }).first();
    await expect(addButton).toBeVisible();
    await addButton.click();
    await expect(page.getByRole('heading', { name: '模型接入' })).toBeVisible({ timeout: 10_000 });
    await capture(page, testInfo, 'remediation-task-routing-empty');
  });

  test('scenario 10: task routing links to reliability for fallback order', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '任务路由' }).click();

    await expect(page.getByText('备用顺序：').first()).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /前往可靠性设置/ }).click();
    await expect(page.getByText('执行后端故障切换').first()).toBeVisible({ timeout: 10_000 });
    await capture(page, testInfo, 'remediation-routing-to-reliability');
  });

  test('scenario 11: reliability view renders failover card and model fallback editor', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '可靠性' }).click();

    await expect(page.getByText('执行后端故障切换').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('模型备用顺序').first()).toBeVisible();
    await capture(page, testInfo, 'remediation-reliability-view');
  });

  test('scenario 12: overview task matrix renders per-task status on the plain path', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '总览' }).click();

    await expect(
      page.getByText(/待配置|未配置/).first(),
    ).toBeVisible({ timeout: 10_000 });
    await capture(page, testInfo, 'remediation-overview-matrix');
  });

  test('scenario 13: MARKET_REVIEW_REGION renders as a checkbox group with localized labels', async ({ page }, testInfo) => {
    await openSettings(page);
    await page.getByRole('button', { name: '系统与安全' }).click();
    await page.waitForTimeout(500);

    const group = page.getByTestId('multi-enum-MARKET_REVIEW_REGION');
    await group.scrollIntoViewIfNeeded();
    await expect(group).toBeVisible({ timeout: 10_000 });
    await expect(group.getByText('A 股（cn）')).toBeVisible();
    await expect(group.getByText('港股（hk）')).toBeVisible();
    await expect(group.getByText('全部市场（both）')).toBeVisible();
    await capture(page, testInfo, 'remediation-market-region-checkboxes');
  });

  test('scenario 14: notification routing fields render as checkbox groups', async ({ page }, testInfo) => {
    await openSettings(page);
    await page.getByRole('button', { name: '告警与自动化' }).click();
    await page.waitForTimeout(500);

    const group = page.getByTestId('multi-enum-NOTIFICATION_REPORT_CHANNELS');
    await group.scrollIntoViewIfNeeded();
    await expect(group).toBeVisible({ timeout: 10_000 });
    await capture(page, testInfo, 'remediation-notification-checkboxes');
  });

  test('scenario 15: editing a checkbox field marks the draft dirty and reset asks for confirmation', async ({ page }, testInfo) => {
    await openSettings(page);
    await page.getByRole('button', { name: '系统与安全' }).click();

    const group = page.getByTestId('multi-enum-MARKET_REVIEW_REGION');
    await group.scrollIntoViewIfNeeded();
    await expect(group).toBeVisible({ timeout: 10_000 });
    await group.getByText('美股（us）').click();

    const saveButton = page.getByRole('button', { name: /保存配置/ });
    await expect(saveButton).toBeEnabled();

    await page.getByRole('button', { name: '重置' }).click();
    await expect(page.getByText(/放弃未保存|确认|恢复/).first()).toBeVisible({ timeout: 5_000 });
    await capture(page, testInfo, 'remediation-dirty-and-reset');
  });

  test('scenario 16: english UI uses connections terminology', async ({ page }, testInfo) => {
    await login(page);
    await page.getByRole('button', { name: '切换界面语言' }).click();
    await page.getByRole('link', { name: 'Settings' }).click();
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByRole('heading', { name: 'System settings' })).toBeVisible({ timeout: 15_000 });

    await page.getByRole('button', { name: 'AI & Models' }).click();
    await expect(page.getByRole('tab', { name: 'Connections' })).toBeVisible({ timeout: 10_000 });

    // Overview view describes the entry with "model connections" terminology.
    await page.getByRole('tab', { name: 'Overview' }).click();
    await expect(page.getByText(/model connections/i).first()).toBeVisible({ timeout: 10_000 });

    await page.getByRole('tab', { name: 'Connections' }).click();
    await expect(page.getByRole('heading', { name: 'Model access' })).toBeVisible({ timeout: 10_000 });

    const content = await page.locator('main, body').first().innerText();
    expect(content).not.toContain('model channels');
    await capture(page, testInfo, 'remediation-english-terminology');
  });

  test('scenario 17: mobile viewport can reach AI connections view', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);

    const menuButton = page.getByRole('button', { name: '打开导航菜单' });
    await expect(menuButton).toBeVisible({ timeout: 10_000 });
    await menuButton.click();
    // The hidden desktop sidebar keeps its links in the DOM, so scope to the drawer.
    await page.getByRole('dialog').getByRole('link', { name: '设置' }).click();
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByRole('heading', { name: '系统设置' })).toBeVisible({ timeout: 15_000 });

    // Mobile always renders the compact native section selector at 390px.
    const sectionSelect = page.locator('#settings-section-select');
    await expect(sectionSelect).toBeVisible({ timeout: 15_000 });
    await sectionSelect.selectOption('ai_models');
    await expect(page.getByRole('tab', { name: '连接' })).toBeVisible({ timeout: 10_000 });
    await capture(page, testInfo, 'remediation-mobile-connections');
  });

  test('scenario 18: first-run wizard opens with catalog-driven provider list', async ({ page }, testInfo) => {
    await openSettings(page);

    // On the plain path setup is never complete, so the quick-setup banner
    // (settings overview -> base category) must expose the wizard entry.
    const wizardButton = page.getByRole('button', { name: /启动向导/ }).first();
    await expect(wizardButton).toBeVisible({ timeout: 15_000 });
    await expect(wizardButton).toBeEnabled({ timeout: 10_000 });
    await wizardButton.click();
    await page.waitForTimeout(500);

    const content = await page.locator('main, body').first().innerText();
    expect(content).toMatch(/DeepSeek|OpenAI|Ollama|云 API|本机 CLI/);
    await capture(page, testInfo, 'remediation-first-run-wizard');
  });
});
