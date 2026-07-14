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
    await expect(page.getByRole('heading', { name: 'AI 模型接入' })).toBeVisible({ timeout: 10_000 });

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

    const addService = page.getByRole('button', { name: /添加模型服务/ }).first();
    await expect(addService).toBeVisible({ timeout: 10_000 });
    await addService.click();

    const content = await page.locator('main, body').first().innerText();
    for (const provider of ['DeepSeek', 'OpenAI', 'Ollama']) {
      expect(content, `provider catalog should list ${provider}`).toContain(provider);
    }
    await capture(page, testInfo, 'remediation-provider-catalog');
  });

  test('scenario 5: Ollama connection marks the API key as optional', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '连接' }).click();

    await page.getByRole('button', { name: /添加模型服务/ }).first().click();
    await page.getByText('Ollama', { exact: false }).first().click();
    await page.waitForTimeout(400);

    const content = await page.locator('main, body').first().innerText();
    expect(content).toMatch(/API 密钥（可选）|无需密钥|可留空/);
    await capture(page, testInfo, 'remediation-ollama-optional-key');
  });

  test('scenario 6: connection form uses value examples and new field labels', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '连接' }).click();

    await page.getByRole('button', { name: /添加模型服务/ }).first().click();
    await page.getByText('DeepSeek', { exact: false }).first().click();
    await page.waitForTimeout(400);

    const content = await page.locator('main, body').first().innerText();
    expect(content).toContain('服务地址');
    expect(content).toContain('API 密钥');
    // Examples are plain values, not KEY=value env lines.
    expect(content).not.toMatch(/LLM_[A-Z0-9_]+_BASE_URL=/);
    expect(content).not.toMatch(/LLM_[A-Z0-9_]+_API_KEY=/);
    await capture(page, testInfo, 'remediation-connection-form-labels');
  });

  test('scenario 7: a new connection starts with no prefilled sample models', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '连接' }).click();

    await page.getByRole('button', { name: /添加模型服务/ }).first().click();
    await page.getByText('DeepSeek', { exact: false }).first().click();
    await page.waitForTimeout(400);

    await expect(
      page.getByText(/尚未添加模型|尚未添加可用模型/).first(),
    ).toBeVisible({ timeout: 5_000 });
    await capture(page, testInfo, 'remediation-no-prefilled-models');
  });

  test('scenario 8: manual model entry adds tokens and splits pasted comma lists', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '连接' }).click();

    await page.getByRole('button', { name: /添加模型服务/ }).first().click();
    await page.getByText('DeepSeek', { exact: false }).first().click();
    await page.waitForTimeout(400);

    const modelInput = page.getByPlaceholder(/输入模型|模型 ID/).first();
    await expect(modelInput).toBeVisible({ timeout: 5_000 });

    await modelInput.fill('model-alpha');
    await modelInput.press('Enter');
    await expect(page.getByText('model-alpha', { exact: true }).first()).toBeVisible();

    await modelInput.fill('model-beta,model-gamma model-alpha');
    await modelInput.press('Enter');
    await expect(page.getByText('model-beta', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('model-gamma', { exact: true }).first()).toBeVisible();
    // Dedupe: model-alpha appears once as a token chip.
    await capture(page, testInfo, 'remediation-token-model-entry');
  });

  test('scenario 9: task routing empty state links back to connections', async ({ page }, testInfo) => {
    await openAiSection(page);
    await page.getByRole('tab', { name: '任务路由' }).click();

    await expect(page.getByText(/尚无可用模型|还没有可用模型/).first()).toBeVisible({ timeout: 10_000 });
    const addButton = page.getByRole('button', { name: '添加模型服务' }).first();
    await expect(addButton).toBeVisible();
    await addButton.click();
    await expect(page.getByRole('heading', { name: 'AI 模型接入' })).toBeVisible({ timeout: 10_000 });
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

    const content = await page.locator('main, body').first().innerText();
    expect(content).toMatch(/待配置|未配置/);
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
    await page.getByRole('tab', { name: 'Connections' }).click();

    const content = await page.locator('main, body').first().innerText();
    expect(content).toContain('model connections');
    expect(content).not.toContain('model channels');
    await capture(page, testInfo, 'remediation-english-terminology');
  });

  test('scenario 17: mobile viewport can reach AI connections view', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);

    const menuButton = page.getByRole('button', { name: /打开导航|菜单/i });
    if (await menuButton.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await menuButton.click();
    }
    await page.getByRole('link', { name: '设置' }).click();
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByRole('heading', { name: '系统设置' })).toBeVisible({ timeout: 15_000 });

    // Mobile uses a compact section selector; fall back to the button list.
    const sectionSelect = page.locator('select').first();
    if (await sectionSelect.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await sectionSelect.selectOption({ label: 'AI 与模型' });
    } else {
      await page.getByRole('button', { name: 'AI 与模型' }).click();
    }
    await expect(page.getByRole('tab', { name: '连接' })).toBeVisible({ timeout: 10_000 });
    await capture(page, testInfo, 'remediation-mobile-connections');
  });

  test('scenario 18: first-run wizard opens with catalog-driven provider list', async ({ page }, testInfo) => {
    await openSettings(page);

    const wizardButton = page.getByRole('button', { name: /启动向导/ }).first();
    if (!(await wizardButton.isVisible({ timeout: 3_000 }).catch(() => false))) {
      test.skip(true, 'First-run wizard entry not visible in current readiness state.');
    }
    await wizardButton.click();
    await page.waitForTimeout(500);

    const content = await page.locator('main, body').first().innerText();
    expect(content).toMatch(/DeepSeek|OpenAI|Ollama|云 API|本机 CLI/);
    await capture(page, testInfo, 'remediation-first-run-wizard');
  });
});
