import { expect, test, type Page } from '@playwright/test';
import { UI_TEXT } from '../src/i18n/uiText';
import { ALERT_PAGE_TEXT } from '../src/locales/alerts';
import { BACKTEST_TEXT } from '../src/locales/backtest';
import { PORTFOLIO_TEXT } from '../src/locales/portfolio';
import { SCREENING_TEXT } from '../src/locales/screening';
import { loginAsE2eAdmin, getE2eAuthStatus } from './auth-fixture';

const fakeProviderPort = Number(process.env.DSA_WEB_SMOKE_PROVIDER_PORT || 18101);

async function switchToEnglish(page: Page) {
  const toggle = page.getByRole('button', { name: '切换界面语言' });
  await expect(toggle).toBeVisible();
  await toggle.click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
}

async function loginInEnglish(page: Page) {
  await loginAsE2eAdmin(page);
  await switchToEnglish(page);
}

test.describe('complete UI i18n acceptance', () => {
  test('initialization, switching, persistence, history, mobile navigation, and theme remain localized', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN'); // 1
    await switchToEnglish(page); // 2
    await expect(page.getByRole('link', { name: 'Home' })).toBeVisible(); // 3
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible(); // 4
    await expect(page.getByRole('button', { name: 'Switch UI language' })).toBeVisible(); // 5
    expect(await page.evaluate(() => localStorage.getItem('dsa.uiLanguage'))).toBe('en'); // 6

    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en'); // 7
    await page.getByRole('link', { name: 'Ask' }).click();
    await page.goBack();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en'); // 8
    await page.goForward();
    await expect(page.getByText(UI_TEXT.en['chat.title'], { exact: true }).first()).toBeVisible(); // 9

    await page.setViewportSize({ width: 390, height: 844 });
    const openNavigation = page.getByRole('button', { name: /Open navigation|Menu/i });
    if (await openNavigation.isVisible().catch(() => false)) await openNavigation.click();
    const mobileBacktestLink = page.getByRole('link', { name: 'Backtest' });
    await expect(mobileBacktestLink).toBeVisible(); // 10
    await mobileBacktestLink.click();

    const themeToggle = page.getByRole('button', { name: 'Toggle theme' }).first();
    await themeToggle.click();
    await page.getByRole('menuitemradio', { name: 'Dark', exact: true }).click();
    await expect(page.locator('html')).toHaveClass(/dark/); // 11

    await page.getByRole('button', { name: 'Switch UI language' }).click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN'); // 12
  });

  test('login supports English for both first setup and returning admin states', async ({ page }) => {
    const status = await getE2eAuthStatus(page);
    await page.addInitScript(() => localStorage.setItem('dsa.uiLanguage', 'en'));
    await page.goto('/login');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en'); // 13
    await expect(page.getByRole('heading', { name: status.passwordSet ? 'Admin login' : 'Set initial password' })).toBeVisible(); // 14
    await expect(page.getByRole('button', { name: status.passwordSet ? 'Enter workspace' : 'Finish setup and sign in' })).toBeVisible(); // 15
  });

  test('every first-level route renders English chrome and an English document title', async ({ page }) => {
    await loginInEnglish(page);
    const routes = [
      { path: '/', text: UI_TEXT.en['home.analyze'], title: UI_TEXT.en['home.pageTitle'] },
      { path: '/chat', text: UI_TEXT.en['chat.title'], title: UI_TEXT.en['chat.pageTitle'] },
      { path: '/screening', text: SCREENING_TEXT.en.title, title: SCREENING_TEXT.en.documentTitle },
      { path: '/portfolio', text: PORTFOLIO_TEXT.en.title, title: PORTFOLIO_TEXT.en.documentTitle },
      { path: '/decision-signals', text: UI_TEXT.en['decisionSignals.title'], title: UI_TEXT.en['decisionSignals.pageTitle'] },
      { path: '/backtest', text: BACKTEST_TEXT.en.runBacktest, title: BACKTEST_TEXT.en.documentTitle },
      { path: '/alerts', text: ALERT_PAGE_TEXT.en.title, title: ALERT_PAGE_TEXT.en.documentTitle },
      { path: '/usage', text: UI_TEXT.en['usage.title'], title: UI_TEXT.en['usage.title'] },
      { path: '/settings', text: UI_TEXT.en['settings.pageTitle'], title: UI_TEXT.en['settings.pageTitle'] },
      { path: '/missing-i18n-route', text: UI_TEXT.en['notFound.title'], title: UI_TEXT.en['notFound.pageTitle'] },
    ];

    for (const route of routes) {
      await page.goto(route.path);
      await expect(page.getByText(route.text, { exact: true }).first()).toBeVisible({ timeout: 15_000 });
      await expect(page).toHaveTitle(new RegExp(route.title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'));
    }
    expect(routes).toHaveLength(10); // 16-25
  });

  test('English Settings localizes model access, discovery success, and discovery failure', async ({ page }) => {
    await loginInEnglish(page);
    await page.goto('/settings?section=ai_models&view=connections');
    await expect(page.getByRole('heading', { name: 'Model access' })).toBeVisible({ timeout: 15_000 }); // 26
    await page.getByRole('button', { name: /Add model service/ }).first().click();
    const dialog = page.getByRole('dialog', { name: 'Add model service' });
    await expect(dialog).toBeVisible(); // 27
    await dialog.getByLabel('Choose model provider').click();
    await page.locator('[role="option"][data-value="custom"]').click();
    await dialog.getByRole('button', { name: 'Next' }).click();
    await dialog.getByLabel('Connection name').fill(`i18n_${Date.now()}`);
    await dialog.getByLabel('Base URL').fill(`http://127.0.0.1:${fakeProviderPort}/v1`);
    await dialog.getByRole('button', { name: 'Get models' }).click();
    await expect(dialog.getByText('Found 3 models')).toBeVisible({ timeout: 20_000 }); // 28

    await dialog.getByLabel('Base URL').fill(`http://127.0.0.1:${fakeProviderPort}/missing`);
    await dialog.getByRole('button', { name: 'Get models' }).click();
    await expect(dialog.getByText(/Model discovery|failed|Request/i).last()).toBeVisible({ timeout: 20_000 }); // 29
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeVisible(); // 30
  });

  test('a Chinese server diagnostic is not the primary English error', async ({ page }) => {
    await page.route('**/api/v1/system/config/llm/available-models**', async (route) => {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'catalog_unavailable', message: '中文原始诊断' }) });
    });
    await loginInEnglish(page);
    await page.goto('/settings?section=ai_models&view=overview');
    await expect(page.getByText('Failed to load available models')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('中文原始诊断', { exact: true })).toHaveCount(0);
  });
});
