import { expect, test, type Page } from '@playwright/test';
import { getE2eAuthStatus, loginAsE2eAdmin } from './auth-fixture';


async function captureSmokeScreenshot(page: Page, testInfo: { outputPath: (name: string) => string }, name: string, options: { fullPage?: boolean } = {}) {
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({
    path,
    fullPage: options.fullPage ?? true,
  });
  await testInfo.attach(name, {
    path,
    contentType: 'image/png',
  });
}

async function login(page: Page) {
  await loginAsE2eAdmin(page);
  await page.waitForTimeout(1000);
}

const alphaSiftStrategy = {
  id: 'dual_low',
  name: '双低选股',
  description: '中文内置策略描述',
  category: '价值',
};

const emptyAlphaSiftHotspots = {
  enabled: true,
  provider: 'akshare',
  hotspots: [],
  hotspot_count: 0,
  message: null,
};

async function createPortfolioAccount(page: Page, suffix: string): Promise<number> {
  const response = await page.request.post('/api/v1/portfolio/accounts', {
    data: {
      name: `E2E ${suffix} ${Date.now()}`,
      broker: 'e2e',
      market: 'cn',
      base_currency: 'CNY',
      owner_id: 'playwright',
    },
  });
  expect(response.ok(), `account seed failed (${response.status()}): ${await response.text()}`).toBe(true);
  const account = await response.json() as { id: number };
  return account.id;
}

async function selectPortfolioAccount(page: Page, accountId: number) {
  await page.getByRole('combobox', { name: '账户视图' }).click();
  await page.locator(`[role="option"][data-value="${accountId}"]`).click();
}

function alertRule(id: number, name: string) {
  return {
    id,
    name,
    target_scope: 'single_symbol',
    target: id === 1 ? '600519' : 'AAPL',
    alert_type: 'price_cross',
    parameters: { direction: 'above', price: 100 + id },
    severity: 'warning',
    enabled: true,
    source: 'api',
    created_at: '2026-07-15T10:00:00',
    updated_at: '2026-07-15T10:00:00',
  };
}

test.describe('web smoke', () => {
  test.use({ locale: 'zh-CN' });

  test('login page renders password form', async ({ page }, testInfo) => {
    const status = await getE2eAuthStatus(page);
    expect(status.loggedIn).toBe(false);
    await page.goto('/login');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/\/login(?:\?|$)/);
    await expect(page.getByRole('heading', { name: 'StockPulse', exact: true })).toBeVisible();

    const expectedHeading = status.passwordSet ? '管理员登录' : '设置初始密码';
    await expect(page.getByRole('heading', { name: expectedHeading })).toBeVisible();

    // Check for password input
    await expect(page.locator('#password')).toBeVisible();

    // Check for submit button
    await expect(page.getByRole('button', { name: /授权进入工作台|完成设置并登录/ })).toBeVisible();

    await captureSmokeScreenshot(page, testInfo, 'smoke-login-page-zh');
  });

  test('home page shows analysis entry and history panel after login', async ({ page }, testInfo) => {
    await login(page);

    const stockInput = page.getByPlaceholder('输入股票代码或名称，如 600519、贵州茅台、AAPL');
    await expect(stockInput).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('link', { name: '首页' })).toBeVisible();
    await expect(page.getByRole('link', { name: '问股' })).toBeVisible();
    await expect(page.getByRole('button', { name: '历史', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '个股栏' })).toBeVisible();

    await stockInput.fill('600519');
    const analyzeButton = page.getByRole('button', { name: '分析', exact: true });
    await expect(analyzeButton).toBeVisible();

    await captureSmokeScreenshot(page, testInfo, 'smoke-home-page-zh', { fullPage: true });
  });

  test('chat page allows entering a question and starts a request', async ({ page }) => {
    await login(page);

    // Navigate to chat page by clicking the link
    await page.getByRole('link', { name: '问股' }).click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    await expect(page.getByTestId('chat-workspace')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('chat-session-list-scroll')).toBeVisible();
    await expect(page.getByTestId('chat-message-scroll')).toBeVisible();

    const input = page.getByPlaceholder(/分析 600519/);
    await expect(input).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('策略', { exact: true })).toBeVisible();

    const prompt = '请简要分析 600519';
    await input.fill(prompt);
    await page.getByRole('button', { name: '发送', exact: true }).click();

    await expect(page.locator('p').filter({ hasText: prompt }).last()).toBeVisible({ timeout: 5000 });
  });

  test('chat page uses accessible labels instead of native title attributes for key actions', async ({ page }) => {
    await login(page);

    await page.getByRole('link', { name: '问股' }).click();
    await page.waitForLoadState('domcontentloaded');

    const sendButton = page.getByRole('button', { name: '发送' });
    const composer = page.getByPlaceholder(/分析 600519/);

    await expect(page.getByTestId('chat-workspace')).toBeVisible({ timeout: 10_000 });
    await expect(sendButton).toBeVisible({ timeout: 10_000 });
    await expect(composer).toBeVisible({ timeout: 10_000 });

    await expect(sendButton).not.toHaveAttribute('title', /.+/);
    await expect(composer).not.toHaveAttribute('title', /.+/);
  });

  test('mobile shell opens navigation drawer after login', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);

    // Try to open navigation menu
    const menuButton = page.getByRole('button', { name: /打开导航|菜单/i });
    if (await menuButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await menuButton.click();
    }

    // Check if navigation is visible
    await expect(page.getByRole('link', { name: '回测' })).toBeVisible({ timeout: 5000 });

    await captureSmokeScreenshot(page, testInfo, 'smoke-mobile-shell-nav');
  });

  test('settings page renders grouped autosave controls without a global Save', async ({ page }, testInfo) => {
    await login(page);

    // Navigate to settings page by clicking the link
    await page.getByRole('link', { name: '设置' }).click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    // Use heading role for more precise selection
    await expect(page.getByRole('heading', { name: '系统设置' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: '重置当前分组' })).toBeVisible();
    await expect(page.getByRole('button', { name: /保存配置/ })).toHaveCount(0);

    await captureSmokeScreenshot(page, testInfo, 'smoke-settings-page-zh');
  });

  test('language switch updates UI copy and persists after page refresh', async ({ page }, testInfo) => {
    await login(page);

    const languageToggle = page.getByRole('button', { name: '切换界面语言' });
    await expect(languageToggle).toBeVisible();
    await expect(page.getByRole('link', { name: '设置' })).toBeVisible();
    await expect(page.getByRole('link', { name: '首页' })).toBeVisible();

    await languageToggle.click();

    const englishLanguageToggle = page.getByRole('button', { name: 'Switch UI language' });
    await expect(englishLanguageToggle).toBeVisible();
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();
    await captureSmokeScreenshot(page, testInfo, 'smoke-home-page-en');

    expect(await page.evaluate(() => localStorage.getItem('dsa.uiLanguage'))).toBe('en');

    await page.reload();
    await page.waitForLoadState('domcontentloaded');

    await expect(englishLanguageToggle).toBeVisible();
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();

    await page.getByRole('link', { name: 'Settings' }).click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    await expect(page.getByRole('heading', { name: 'System settings' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: 'Reset current group' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save configuration' })).toHaveCount(0);

    await captureSmokeScreenshot(page, testInfo, 'smoke-settings-page-en');
  });

  test('backtest page renders filter controls after login', async ({ page }, testInfo) => {
    await login(page);

    // Navigate to backtest page by clicking the link
    await page.getByRole('link', { name: '回测' }).click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    // Check for filter controls
    const filterInput = page.getByPlaceholder('按股票代码筛选（留空表示全部）');
    await expect(filterInput).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: '筛选' })).toBeVisible();
    await expect(page.getByRole('button', { name: '运行回测' })).toBeVisible();

    await captureSmokeScreenshot(page, testInfo, 'smoke-backtest-page-zh', { fullPage: true });
  });

  test('[scenario 11] Chat handles IME, streaming, failure, and explicit retry', async ({ page }) => {
    let streamCalls = 0;
    let releaseFirstStream!: () => void;
    const firstStreamGate = new Promise<void>((resolve) => {
      releaseFirstStream = resolve;
    });
    await page.route('**/api/v1/agent/chat/stream', async (route) => {
      streamCalls += 1;
      if (streamCalls === 1) {
        await firstStreamGate;
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: 'data: {"type":"done","success":true,"content":"首次流式回复"}\n\n',
        });
        return;
      }
      if (streamCalls === 2) {
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: 'data: {"type":"error","error_code":"agent_stream_failed","message":"temporary stream failure"}\n\n',
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: 'data: {"type":"done","success":true,"content":"重试成功回复"}\n\n',
      });
    });

    await login(page);
    await page.goto('/chat');
    const input = page.getByPlaceholder(/分析 600519/);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill('输入法组合文本');
    await input.evaluate((element) => {
      const event = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true });
      Object.defineProperty(event, 'isComposing', { value: true });
      Object.defineProperty(event, 'keyCode', { value: 229 });
      element.dispatchEvent(event);
    });
    await page.waitForTimeout(100);
    expect(streamCalls).toBe(0);
    await expect(input).toHaveValue('输入法组合文本');

    await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect(page.getByRole('button', { name: '停止生成' })).toBeVisible();
    releaseFirstStream();
    await expect(page.getByText('首次流式回复')).toBeVisible({ timeout: 10_000 });

    await input.fill('失败后重试');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    const retry = page.getByRole('button', { name: '重试' });
    await expect(retry).toBeVisible({ timeout: 10_000 });
    await retry.click();
    await expect(page.getByText('重试成功回复')).toBeVisible({ timeout: 10_000 });
    expect(streamCalls).toBe(3);
  });

  test('[scenario 12] Chat restores the session named by its URL', async ({ page }) => {
    await page.route('**/api/v1/agent/chat/sessions**', async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname.endsWith('/session-e2e')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            messages: [
              { id: 'm1', role: 'user', content: '恢复的问题', created_at: '2026-07-15T10:00:00Z' },
              { id: 'm2', role: 'assistant', content: 'URL 恢复的回答', created_at: '2026-07-15T10:00:01Z' },
            ],
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sessions: [{
            session_id: 'session-e2e',
            title: 'URL recovery',
            message_count: 2,
            created_at: '2026-07-15T10:00:00Z',
            last_active: '2026-07-15T10:00:01Z',
          }],
        }),
      });
    });

    await login(page);
    await page.goto('/chat?session=session-e2e');
    await expect(page).toHaveURL(/session=session-e2e/);
    await expect(page.getByText('URL 恢复的回答')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: '切换到对话 URL recovery' })).toHaveAttribute('aria-current', 'page');
  });

  test('[scenario 13] Screening localizes built-in strategy IDs in English', async ({ page }) => {
    await page.route('**/api/v1/alphasift/**', async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname.endsWith('/status')) {
        await route.fulfill({ json: { enabled: true, available: true } });
      } else if (pathname.endsWith('/strategies')) {
        await route.fulfill({ json: { enabled: true, strategies: [alphaSiftStrategy], strategy_count: 1 } });
      } else if (pathname.endsWith('/hotspots')) {
        await route.fulfill({ json: emptyAlphaSiftHotspots });
      } else {
        await route.continue();
      }
    });

    await login(page);
    await page.getByRole('button', { name: '切换界面语言' }).click();
    await page.goto('/screening');
    await expect(page.getByText('Dual-Low Selection', { exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('中文内置策略描述', { exact: true })).toHaveCount(0);
  });

  test('[scenario 14] Screening task success, failure, and session recovery stay actionable', async ({ page }) => {
    await page.addInitScript(() => {
      sessionStorage.setItem('dsa.alphasift.activeScreenTask.v1', JSON.stringify({
        taskId: 'restore-task', market: 'cn', strategy: 'dual_low', maxResults: 3,
      }));
    });
    let submittedTasks = 0;
    const completedResult = (name: string) => ({
      enabled: true,
      candidates: [{
        rank: 1,
        code: name === 'Recovered Candidate' ? '600519' : 'AAPL',
        name,
        score: 0.91,
        reason: 'deterministic candidate',
        factor_scores: {},
        post_analysis_summaries: {},
        raw: { signal: 'watch' },
      }],
      candidate_count: 1,
      strategy: 'dual_low',
      market: 'cn',
    });
    await page.route('**/api/v1/alphasift/**', async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      if (pathname.endsWith('/status')) {
        await route.fulfill({ json: { enabled: true, available: true } });
      } else if (pathname.endsWith('/strategies')) {
        await route.fulfill({ json: { enabled: true, strategies: [alphaSiftStrategy], strategy_count: 1 } });
      } else if (pathname.endsWith('/hotspots')) {
        await route.fulfill({ json: emptyAlphaSiftHotspots });
      } else if (pathname.endsWith('/screen/tasks') && request.method() === 'POST') {
        submittedTasks += 1;
        const taskId = submittedTasks === 1 ? 'failed-task' : 'success-task';
        await route.fulfill({
          status: 202,
          json: {
            task_id: taskId,
            trace_id: `trace-${taskId}`,
            status: 'pending',
            message: 'queued',
            message_code: 'alphasift_screen_queued',
            revision: 1,
            updated_at: '2026-07-15T10:00:00Z',
            strategy: 'dual_low',
            market: 'cn',
            max_results: 3,
          },
        });
      } else if (pathname.endsWith('/screen/tasks/restore-task')) {
        await route.fulfill({ json: {
          task_id: 'restore-task', status: 'completed', progress: 100, revision: 2,
          updated_at: '2026-07-15T10:00:02Z', result: completedResult('Recovered Candidate'),
        } });
      } else if (pathname.endsWith('/screen/tasks/failed-task')) {
        await route.fulfill({ json: {
          task_id: 'failed-task', status: 'failed', progress: 100, revision: 2,
          message_code: 'task_failed', error_code: 'task_execution_failed', error: 'raw failure',
          updated_at: '2026-07-15T10:00:03Z',
        } });
      } else if (pathname.endsWith('/screen/tasks/success-task')) {
        await route.fulfill({ json: {
          task_id: 'success-task', status: 'completed', progress: 100, revision: 2,
          updated_at: '2026-07-15T10:00:04Z', result: completedResult('Fresh Candidate'),
        } });
      } else {
        await route.continue();
      }
    });

    await login(page);
    await page.goto('/screening');
    await expect(page.getByText('Recovered Candidate')).toBeVisible({ timeout: 10_000 });

    const run = page.getByRole('button', { name: '运行选股' });
    await run.click();
    await expect(page.getByRole('alert').filter({ hasText: '任务未能完成，请查看诊断后重试' })).toBeVisible({ timeout: 10_000 });
    await run.click();
    await expect(page.getByText('Fresh Candidate')).toBeVisible({ timeout: 10_000 });
    expect(submittedTasks).toBe(2);
  });

  test('[scenario 15] Alerts create failure keeps Modal input intact', async ({ page }) => {
    await page.route('**/api/v1/alerts/**', async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      if (pathname.endsWith('/rules') && request.method() === 'POST') {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'alert_create_failed', message: 'deterministic create failure' }),
        });
      } else if (pathname.endsWith('/rules')) {
        await route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } });
      } else if (pathname.endsWith('/triggers') || pathname.endsWith('/notifications')) {
        await route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } });
      } else {
        await route.continue();
      }
    });

    await login(page);
    await page.goto('/alerts');
    await page.getByRole('button', { name: '创建告警规则' }).click();
    const dialog = page.getByRole('dialog', { name: '创建告警规则' });
    await dialog.getByLabel('标的代码').fill('aapl');
    await dialog.getByLabel('价格阈值').fill('200');
    await dialog.getByRole('button', { name: '创建规则' }).click();
    await expect(dialog.getByRole('alert')).toBeVisible({ timeout: 10_000 });
    await expect(dialog.getByLabel('标的代码')).toHaveValue('aapl');
    await expect(dialog.getByLabel('价格阈值')).toHaveValue('200');
  });

  test('[scenario 16] Alerts tracks two concurrent rule operations independently', async ({ page }) => {
    const gates = new Map<number, Promise<void>>();
    const releases = new Map<number, () => void>();
    for (const id of [1, 2]) {
      gates.set(id, new Promise<void>((resolve) => releases.set(id, resolve)));
    }
    const started: number[] = [];
    await page.route('**/api/v1/alerts/**', async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      const disableMatch = pathname.match(/\/rules\/(\d+)\/disable$/);
      if (disableMatch) {
        const id = Number(disableMatch[1]);
        started.push(id);
        await gates.get(id);
        await route.fulfill({ json: { ...alertRule(id, id === 1 ? '并发规则一' : '并发规则二'), enabled: false } });
      } else if (pathname.endsWith('/rules')) {
        await route.fulfill({
          json: { items: [alertRule(1, '并发规则一'), alertRule(2, '并发规则二')], total: 2, page: 1, page_size: 20 },
        });
      } else if (pathname.endsWith('/triggers') || pathname.endsWith('/notifications')) {
        await route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } });
      } else {
        await route.continue();
      }
    });

    await login(page);
    await page.goto('/alerts');
    const firstRow = page.locator('tr').filter({ hasText: '并发规则一' });
    const secondRow = page.locator('tr').filter({ hasText: '并发规则二' });
    await firstRow.getByRole('button', { name: '停用' }).click();
    await expect(secondRow.getByRole('button', { name: '停用' })).toBeEnabled();
    await secondRow.getByRole('button', { name: '停用' }).click();
    await expect.poll(() => started.slice().sort()).toEqual([1, 2]);
    await expect(firstRow.getByRole('button', { name: '停用中' })).toBeVisible();
    await expect(secondRow.getByRole('button', { name: '停用中' })).toBeVisible();
    releases.get(1)?.();
    releases.get(2)?.();
    await expect(firstRow.getByRole('button', { name: '停用' })).toBeVisible({ timeout: 10_000 });
  });

  test('[scenario 17] Portfolio retries a timed-out write without duplicate ledger rows', async ({ page }) => {
    await login(page);
    const accountId = await createPortfolioAccount(page, 'idempotency');
    const operationIds: string[] = [];
    await page.route('**/api/v1/portfolio/trades', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue();
        return;
      }
      const payload = route.request().postDataJSON() as { operation_id: string };
      operationIds.push(payload.operation_id);
      const upstream = await route.fetch();
      if (operationIds.length === 1) {
        expect(upstream.ok()).toBe(true);
        await route.abort('timedout');
        return;
      }
      await route.fulfill({ response: upstream });
    });

    await page.goto('/portfolio');
    await selectPortfolioAccount(page, accountId);
    const enterTrade = page.getByRole('button', { name: '录入交易' });
    await expect(enterTrade).toBeEnabled({ timeout: 15_000 });
    await enterTrade.click();
    const dialog = page.getByRole('dialog', { name: '手工录入：交易' });
    await dialog.getByLabel('股票代码').fill('600519');
    await dialog.getByLabel('数量').fill('10');
    await dialog.getByLabel('成交价').fill('100');
    await dialog.getByRole('button', { name: '提交交易' }).click();
    await expect(dialog.getByRole('alert')).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByLabel('股票代码')).toHaveValue('600519');
    await dialog.getByRole('button', { name: '提交交易' }).click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });

    expect(operationIds).toHaveLength(2);
    expect(operationIds[1]).toBe(operationIds[0]);
    const ledgerResponse = await page.request.get(`/api/v1/portfolio/trades?account_id=${accountId}&page_size=20`);
    expect(ledgerResponse.ok()).toBe(true);
    const ledger = await ledgerResponse.json() as { total: number; items: unknown[] };
    expect(ledger.total).toBe(1);
    expect(ledger.items).toHaveLength(1);
  });

  test('[scenario 18] Portfolio trade form remains usable at 320px', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await login(page);
    const accountId = await createPortfolioAccount(page, 'mobile');
    await page.goto('/portfolio');
    await selectPortfolioAccount(page, accountId);
    const enterTrade = page.getByRole('button', { name: '录入交易' });
    await expect(enterTrade).toBeEnabled({ timeout: 15_000 });
    await enterTrade.click();
    const dialog = page.getByRole('dialog', { name: '手工录入：交易' });
    await expect(dialog).toBeVisible();
    const quantity = dialog.getByLabel('数量');
    const gridLayout = await quantity.evaluate((element) => {
      const grid = element.closest('.grid');
      return {
        found: grid !== null,
        columns: grid ? getComputedStyle(grid).gridTemplateColumns : '',
      };
    });
    expect(gridLayout.found).toBe(true);
    expect(gridLayout.columns.trim()).not.toBe('');
    expect(gridLayout.columns.trim().split(/\s+/)).toHaveLength(1);
    const submitTrade = dialog.getByRole('button', { name: '提交交易' });
    await expect(submitTrade).toBeVisible();
    expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    const box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(320);
    await submitTrade.scrollIntoViewIfNeeded();
    await expect(submitTrade).toBeInViewport();
    await captureSmokeScreenshot(page, testInfo, 'portfolio-trade-form-320');
  });

  test('[scenario 31] Home completes a submitted task through polling after SSE disconnects', async ({ page }) => {
    await page.addInitScript(() => {
      class ControlledEventSource {
        static instance: ControlledEventSource | null = null;
        onerror: ((event: Event) => void) | null = null;
        constructor() {
          ControlledEventSource.instance = this;
        }
        addEventListener() {}
        close() {}
      }
      Object.defineProperty(window, 'EventSource', { configurable: true, value: ControlledEventSource });
      (window as unknown as { __disconnectTaskStream: () => boolean }).__disconnectTaskStream = () => {
        const instance = ControlledEventSource.instance;
        if (!instance?.onerror) {
          return false;
        }
        instance.onerror(new Event('error'));
        return true;
      };
    });
    let statusPolls = 0;
    await page.route('**/api/v1/analysis/**', async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      if (pathname.endsWith('/analyze') && request.method() === 'POST') {
        await route.fulfill({
          status: 202,
          json: {
            task_id: 'task-disconnect', trace_id: 'trace-disconnect', status: 'pending',
            message: 'queued', message_code: 'analysis_task_queued', revision: 1,
            updated_at: '2026-07-15T10:00:00Z', analysis_phase: 'auto',
          },
        });
      } else if (pathname.endsWith('/analysis/tasks')) {
        await route.fulfill({ json: { tasks: [], total: 0 } });
      } else if (pathname.endsWith('/status/task-disconnect')) {
        statusPolls += 1;
        await route.fulfill({ json: {
          task_id: 'task-disconnect', trace_id: 'trace-disconnect', stock_code: 'AAPL',
          status: 'completed', progress: 100, message_code: 'task_completed', revision: 2,
          updated_at: '2026-07-15T10:00:02Z',
        } });
      } else if (pathname.endsWith('/tasks/task-disconnect/flow')) {
        await route.fulfill({ json: {
          task_id: 'task-disconnect', trace_id: 'trace-disconnect', stock_code: 'AAPL',
          status: 'success', summary: { failed_attempts: 0, fallback_count: 0, data_source_count: 0, event_count: 0 },
          lanes: [], nodes: [], edges: [], events: [], generated_at: '2026-07-15T10:00:02Z',
        } });
      } else {
        await route.continue();
      }
    });

    await login(page);
    const input = page.getByPlaceholder('输入股票代码或名称，如 600519、贵州茅台、AAPL');
    await input.fill('AAPL');
    await page.getByRole('button', { name: '分析', exact: true }).click();
    const task = page.getByTestId('task-panel-item').filter({ hasText: 'AAPL' });
    await expect(task.getByText('等待中')).toBeVisible({ timeout: 10_000 });
    const disconnected = await page.evaluate(() => (
      window as unknown as { __disconnectTaskStream: () => boolean }
    ).__disconnectTaskStream());
    expect(disconnected).toBe(true);
    await expect(task.getByText('已完成', { exact: true })).toBeVisible({ timeout: 10_000 });
    expect(statusPolls).toBeGreaterThan(0);
    await task.getByRole('button', { name: '查看 AAPL 运行流' }).click();
    await expect(page).toHaveURL(/runFlow=task.*taskId=task-disconnect/);
    await expect(page.getByTestId('run-flow-panel')).toBeVisible({ timeout: 10_000 });
  });

  test('[scenario 32] fast history switching ignores the older detail response', async ({ page }) => {
    await login(page);
    const historyResponse = await page.request.get('/api/v1/history?limit=50');
    const history = await historyResponse.json() as {
      items: Array<{ id: number; stock_name?: string; stockName?: string }>;
    };
    const chinese = history.items.find((item) => (item.stock_name ?? item.stockName) === 'E2E Chinese Report');
    const english = history.items.find((item) => (item.stock_name ?? item.stockName) === 'E2E English Report');
    expect(chinese).toBeTruthy();
    expect(english).toBeTruthy();

    let releaseOlder!: () => void;
    const olderGate = new Promise<void>((resolve) => {
      releaseOlder = resolve;
    });
    let markOlderStarted!: () => void;
    const olderStarted = new Promise<void>((resolve) => {
      markOlderStarted = resolve;
    });
    let markOlderFulfilled!: () => void;
    const olderFulfilled = new Promise<void>((resolve) => {
      markOlderFulfilled = resolve;
    });
    await page.route(`**/api/v1/history/${chinese!.id}`, async (route) => {
      markOlderStarted();
      const response = await route.fetch();
      await olderGate;
      await route.fulfill({ response });
      markOlderFulfilled();
    });
    await page.route(`**/api/v1/history/${english!.id}`, async (route) => {
      await route.fulfill({ response: await route.fetch() });
    });

    await page.getByRole('button', { name: /^E2E Chinese Report / }).click();
    await olderStarted;
    await page.getByRole('button', { name: /^E2E English Report / }).click();
    await expect(page.getByText(/E2E_EN_REPORT_BODY_MARKER/).first()).toBeVisible({ timeout: 10_000 });
    releaseOlder();
    await olderFulfilled;
    await expect(page.getByText(/E2E_EN_REPORT_BODY_MARKER/).first()).toBeVisible();
    await expect(page.getByText(/E2E_ZH_REPORT_BODY_MARKER/)).toHaveCount(0);
    await expect(page).toHaveURL(new RegExp(`recordId=${english!.id}`));
  });

  test('[scenario 33] a new Market Review task invalidates the old polling generation', async ({ page }) => {
    let triggerCount = 0;
    let oldStatusCalls = 0;
    let releaseOldStatus!: () => void;
    const oldStatusGate = new Promise<void>((resolve) => {
      releaseOldStatus = resolve;
    });
    let markSecondOldStatusStarted!: () => void;
    const secondOldStatusStarted = new Promise<void>((resolve) => {
      markSecondOldStatusStarted = resolve;
    });
    let markOldStatusFulfilled!: () => void;
    const oldStatusFulfilled = new Promise<void>((resolve) => {
      markOldStatusFulfilled = resolve;
    });
    await page.route('**/api/v1/analysis/market-review', async (route) => {
      triggerCount += 1;
      const taskId = triggerCount === 1 ? 'market-old' : 'market-new';
      await route.fulfill({
        status: 202,
        json: { status: 'accepted', send_notification: true, message: `${taskId} submitted`, task_id: taskId },
      });
    });
    await page.route('**/api/v1/analysis/status/market-*', async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname.endsWith('/market-old')) {
        oldStatusCalls += 1;
        if (oldStatusCalls === 1) {
          await route.fulfill({ json: {
            task_id: 'market-old', status: 'processing', progress: 20,
          } });
          return;
        }
        markSecondOldStatusStarted();
        await oldStatusGate;
        await route.fulfill({ json: {
          task_id: 'market-old', status: 'processing', progress: 20,
          market_review_report: 'OLD_MARKET_REVIEW_MUST_NOT_RENDER',
        } });
        markOldStatusFulfilled();
        return;
      }
      await route.fulfill({ json: {
        task_id: 'market-new', status: 'completed', progress: 100,
        market_review_report: 'NEW_MARKET_REVIEW_RESULT',
        market_review_payload: { kind: 'market_review', language: 'zh', title: 'New review', sections: [] },
      } });
    });

    await login(page);
    const marketReview = page.getByRole('button', { name: '大盘复盘', exact: true });
    await marketReview.click();
    await expect(page.getByText('大盘复盘进行中')).toBeVisible({ timeout: 10_000 });
    await expect(marketReview).toBeEnabled();
    await secondOldStatusStarted;
    await marketReview.click();
    await expect(page.getByText('NEW_MARKET_REVIEW_RESULT')).toBeVisible({ timeout: 10_000 });
    releaseOldStatus();
    await oldStatusFulfilled;
    await page.waitForTimeout(2300);
    expect(oldStatusCalls).toBe(2);
    await expect(page.getByText('OLD_MARKET_REVIEW_MUST_NOT_RENDER')).toHaveCount(0);
  });
});
