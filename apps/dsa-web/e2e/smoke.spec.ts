import { expect, test, type Page } from '@playwright/test';
import { getE2eAuthStatus, loginAsE2eAdmin } from './auth-fixture';
import { resolvePlaywrightPorts } from './playwright-result-paths.mjs';

const { frontendPort } = resolvePlaywrightPorts(process.env);
const localFrontendOrigin = `http://127.0.0.1:${frontendPort}`;

async function login(page: Page) {
  await loginAsE2eAdmin(page);
  await page.waitForTimeout(1000);
}

const uiLanguageSelector = (page: Page) =>
  page.locator('[data-testid="ui-language-selector"]:visible [role="combobox"]').first();

async function openProfileMenu(page: Page) {
  const trigger = page.getByRole('button', { name: 'StockPulse', exact: true }).last();
  if (await trigger.getAttribute('aria-expanded') !== 'true') {
    await trigger.click();
  }
}

async function selectUiLanguage(page: Page, language: 'zh' | 'en') {
  await openProfileMenu(page);
  await uiLanguageSelector(page).click();
  await page.locator(`[role="option"][data-value="${language}"]`).click();
}

async function openLoginAtBrowserOrigin(page: Page, browserOrigin: string) {
  await page.route(`${browserOrigin}/**`, async (route) => {
    const browserUrl = new URL(route.request().url());
    const localUrl = new URL(`${browserUrl.pathname}${browserUrl.search}`, localFrontendOrigin);
    const response = await route.fetch({ url: localUrl.href });
    await route.fulfill({ response });
  });
  await page.goto(`${browserOrigin}/login`);
  await page.waitForLoadState('domcontentloaded');
}

function relativeLuminance([red, green, blue]: number[]) {
  const channels = [red, green, blue].map((value) => {
    const normalized = value / 255;
    return normalized <= 0.04045
      ? normalized / 12.92
      : ((normalized + 0.055) / 1.055) ** 2.4;
  });
  return (0.2126 * channels[0]) + (0.7152 * channels[1]) + (0.0722 * channels[2]);
}

function contrastRatio(foreground: number[], background: number[]) {
  const lighter = Math.max(relativeLuminance(foreground), relativeLuminance(background));
  const darker = Math.min(relativeLuminance(foreground), relativeLuminance(background));
  return (lighter + 0.05) / (darker + 0.05);
}

async function expectSecurityWarningContrast(page: Page, theme: 'light' | 'dark') {
  await page.evaluate((nextTheme) => {
    document.documentElement.classList.remove('light', 'dark');
    document.documentElement.classList.add(nextTheme);
  }, theme);
  const { background, foreground } = await page.locator('[data-connection-status="insecure-http"]').evaluate((element) => {
    type Rgba = [number, number, number, number];

    const parseColor = (value: string): Rgba => {
      const match = value.match(
        /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+))?\s*\)$/,
      );
      if (!match) throw new Error(`Unsupported computed color: ${value}`);
      return [Number(match[1]), Number(match[2]), Number(match[3]), Number(match[4] ?? 1)];
    };

    const composite = (front: Rgba, back: Rgba): Rgba => {
      const alpha = front[3] + (back[3] * (1 - front[3]));
      if (alpha === 0) return [0, 0, 0, 0];
      return [
        ((front[0] * front[3]) + (back[0] * back[3] * (1 - front[3]))) / alpha,
        ((front[1] * front[3]) + (back[1] * back[3] * (1 - front[3]))) / alpha,
        ((front[2] * front[3]) + (back[2] * back[3] * (1 - front[3]))) / alpha,
        alpha,
      ];
    };

    const backgroundLayers: Rgba[] = [];
    for (let current: Element | null = element; current; current = current.parentElement) {
      backgroundLayers.push(parseColor(getComputedStyle(current).backgroundColor));
    }
    let renderedBackground: Rgba = [255, 255, 255, 1];
    for (const layer of backgroundLayers.reverse()) {
      renderedBackground = composite(layer, renderedBackground);
    }
    const renderedForeground = composite(parseColor(getComputedStyle(element).color), renderedBackground);
    return {
      background: renderedBackground.slice(0, 3),
      foreground: renderedForeground.slice(0, 3),
    };
  });
  const ratio = contrastRatio(foreground, background);
  expect(
    ratio,
    `${theme} warning contrast ${ratio.toFixed(2)}:1 for foreground ${foreground.join(',')} on ${background.join(',')}`,
  ).toBeGreaterThanOrEqual(4.5);
}

test.describe('web smoke', () => {
  test.use({ locale: 'zh-CN' });

  test('login page renders password form', async ({ page }) => {
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

    const connectionNotice = page.locator('[data-connection-status]');
    await expect(connectionNotice).toHaveAttribute('data-connection-status', 'local-http');
    await expect(connectionNotice).toHaveText('当前通过本机 HTTP 连接访问；此连接未使用 HTTPS。');
    await expect(page.getByText(/StockPulse-V3-TLS/)).toHaveCount(0);
  });

  test('login page derives HTTPS from the browser origin', async ({ page }) => {
    await openLoginAtBrowserOrigin(page, 'https://secure.stockpulse.test');

    await expect.poll(() => page.evaluate(() => ({
      hostname: window.location.hostname,
      protocol: window.location.protocol,
    }))).toEqual({
      hostname: 'secure.stockpulse.test',
      protocol: 'https:',
    });
    const connectionNotice = page.locator('[data-connection-status]');
    await expect(connectionNotice).toHaveAttribute('data-connection-status', 'https');
    await expect(connectionNotice).toHaveAttribute('role', 'status');
    await expect(connectionNotice).toHaveText('此登录页面使用 HTTPS 加密传输。');
  });

  test('login page warns on non-loopback HTTP from the browser origin', async ({ page }) => {
    await openLoginAtBrowserOrigin(page, 'http://stocks.example.test');

    await expect.poll(() => page.evaluate(() => ({
      hostname: window.location.hostname,
      protocol: window.location.protocol,
    }))).toEqual({
      hostname: 'stocks.example.test',
      protocol: 'http:',
    });
    const connectionNotice = page.locator('[data-connection-status]');
    await expect(connectionNotice).toHaveAttribute('data-connection-status', 'insecure-http');
    await expect(connectionNotice).toHaveAttribute('role', 'alert');
    await expect(connectionNotice).toHaveText(
      '警告：当前连接未使用 HTTPS。登录密码可能在传输中暴露，请改用 HTTPS。',
    );
    await expectSecurityWarningContrast(page, 'light');
    await expectSecurityWarningContrast(page, 'dark');
  });

  test('home page shows analysis entry and history panel after login', async ({ page }) => {
    await login(page);

    const stockInput = page.getByPlaceholder('输入股票代码或名称，如 600519、贵州茅台、AAPL');
    await expect(stockInput).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('link', { name: '首页' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Agent' })).toBeVisible();
    await expect(page.getByRole('combobox', { name: '工作台视图切换' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '个股栏' })).toBeVisible();

    await stockInput.fill('600519');
    const analyzeButton = page.getByRole('button', { name: '分析', exact: true });
    await expect(analyzeButton).toBeVisible();

  });

  test('chat page allows entering a question and starts a request', async ({ page }) => {
    await login(page);

    // Navigate to chat page by clicking the link
    await page.getByRole('link', { name: 'Agent' }).click();
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
    await page.getByRole('button', { name: '发送' }).click();

    await expect(page.locator('p').filter({ hasText: prompt }).last()).toBeVisible({ timeout: 5000 });
  });

  test('chat page uses accessible labels instead of native title attributes for key actions', async ({ page }) => {
    await login(page);

    await page.getByRole('link', { name: 'Agent' }).click();
    await page.waitForLoadState('domcontentloaded');

    const sendButton = page.getByRole('button', { name: '发送' });
    const composer = page.getByPlaceholder(/分析 600519/);

    await expect(page.getByTestId('chat-workspace')).toBeVisible({ timeout: 10_000 });
    await expect(sendButton).toBeVisible({ timeout: 10_000 });
    await expect(composer).toBeVisible({ timeout: 10_000 });

    await expect(sendButton).not.toHaveAttribute('title', /.+/);
    await expect(composer).not.toHaveAttribute('title', /.+/);
  });

  test('mobile shell opens navigation drawer after login', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);

    // Try to open navigation menu
    const menuButton = page.getByRole('button', { name: /打开导航|菜单/i });
    if (await menuButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await menuButton.click();
    }

    // Check if navigation is visible
    await expect(page.getByRole('link', { name: '回测' })).toBeVisible({ timeout: 5000 });

  });

  test('settings page renders without legacy global save actions after login', async ({ page }) => {
    await login(page);

    // Navigate to settings page by clicking the link
    await page.getByRole('link', { name: '设置' }).click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    // Use heading role for more precise selection
    await expect(page.getByRole('heading', { name: '系统设置' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: '重置当前分组' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /保存配置/ })).toHaveCount(0);

  });

  test('language switch updates UI copy and persists after page refresh', async ({ page }) => {
    await login(page);

    await openProfileMenu(page);
    const languageSelector = uiLanguageSelector(page);
    await expect(languageSelector).toBeVisible();
    await expect(page.getByRole('link', { name: '设置' })).toBeVisible();
    await expect(page.getByRole('link', { name: '首页' })).toBeVisible();

    await selectUiLanguage(page, 'en');

    await expect(languageSelector).toHaveAttribute('data-value', 'en');
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();

    expect(await page.evaluate(() => localStorage.getItem('dsa.uiLanguage'))).toBe('en');

    await page.reload();
    await page.waitForLoadState('domcontentloaded');

    await openProfileMenu(page);
    await expect(uiLanguageSelector(page)).toHaveAttribute('data-value', 'en');
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();
    await page.getByRole('button', { name: 'StockPulse', exact: true }).last().click();

    await page.getByRole('link', { name: 'Settings' }).click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    await expect(page.getByRole('heading', { name: 'System settings' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: 'Save configuration' })).toHaveCount(0);

  });

  test('backtest page renders filter controls after login', async ({ page }) => {
    await login(page);

    // Navigate to backtest page by clicking the link
    await page.getByRole('link', { name: '回测' }).click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    // Check for filter controls
    const filterInput = page.getByPlaceholder('按股票代码筛选（留空表示全部）');
    await expect(filterInput).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: '筛选' })).toBeVisible();
    await expect(page.getByRole('button', { name: '运行回测', exact: true })).toBeVisible();

  });
});
