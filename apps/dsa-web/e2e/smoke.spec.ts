import { expect, test, type Page } from '@playwright/test';
import { getE2eAuthStatus, loginAsE2eAdmin } from './auth-fixture';

async function login(page: Page) {
  await loginAsE2eAdmin(page);
  await page.waitForTimeout(1000);
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

  });

  test('home page shows analysis entry and history panel after login', async ({ page }) => {
    await login(page);

    const stockInput = page.getByPlaceholder('输入股票代码或名称，如 600519、贵州茅台、AAPL');
    await expect(stockInput).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('link', { name: '首页' })).toBeVisible();
    await expect(page.getByRole('link', { name: '问股' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '历史', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '个股栏' })).toBeVisible();

    await stockInput.fill('600519');
    const analyzeButton = page.getByRole('button', { name: '分析', exact: true });
    await expect(analyzeButton).toBeVisible();

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
    await page.getByRole('button', { name: '发送' }).click();

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

    const languageSelector = page.locator('select[data-testid="ui-language-selector"]:visible').first();
    await expect(languageSelector).toBeVisible();
    await expect(page.getByRole('link', { name: '设置' })).toBeVisible();
    await expect(page.getByRole('link', { name: '首页' })).toBeVisible();

    await languageSelector.selectOption('en');

    await expect(languageSelector).toHaveValue('en');
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();

    expect(await page.evaluate(() => localStorage.getItem('dsa.uiLanguage'))).toBe('en');

    await page.reload();
    await page.waitForLoadState('domcontentloaded');

    await expect(languageSelector).toHaveValue('en');
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();

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
    await expect(page.getByRole('button', { name: '运行回测' })).toBeVisible();

  });
});
