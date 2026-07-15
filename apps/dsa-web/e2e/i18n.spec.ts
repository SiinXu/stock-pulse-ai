import { expect, test, type Page } from '@playwright/test';
import { UI_TEXT } from '../src/i18n/uiText';
import { ALERT_PAGE_TEXT } from '../src/locales/alerts';
import { BACKTEST_TEXT } from '../src/locales/backtest';
import { PORTFOLIO_TEXT } from '../src/locales/portfolio';
import { REPORT_CHROME_TEXT } from '../src/locales/reportChrome';
import { SCREENING_TEXT } from '../src/locales/screening';
import { loginAsE2eAdmin } from './auth-fixture';

const fakeProviderPort = Number(process.env.DSA_WEB_SMOKE_PROVIDER_PORT || 18101);
const UI_LANGUAGE_STORAGE_KEY = 'dsa.uiLanguage';
const REPORT_ZH_MARKER = 'E2E_ZH_REPORT_BODY_MARKER';
const REPORT_EN_MARKER = 'E2E_EN_REPORT_BODY_MARKER';

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

async function openEnglishRoute(page: Page, path: string) {
  await loginInEnglish(page);
  await page.goto(path);
}

async function mockFirstLoginStatus(page: Page) {
  await page.route('**/api/v1/auth/status', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      authEnabled: true,
      loggedIn: false,
      passwordSet: false,
      passwordChangeable: true,
      setupState: 'no_password',
    }),
  }));
}

async function findSeededReportId(page: Page, stockName: string): Promise<number> {
  const response = await page.request.get('/api/v1/history?limit=50');
  expect(response.ok()).toBe(true);
  const payload = await response.json() as {
    items: Array<{ id: number; stock_name?: string; stockName?: string }>;
  };
  const report = payload.items.find((item) => (item.stock_name ?? item.stockName) === stockName);
  expect(report, `missing seeded report ${stockName}`).toBeTruthy();
  return report!.id;
}

async function openSeededReport(
  page: Page,
  options: { uiLanguage: 'zh' | 'en'; stockName: string; marker: string },
) {
  await loginAsE2eAdmin(page);
  if (options.uiLanguage === 'en') {
    await switchToEnglish(page);
  }
  const recordId = await findSeededReportId(page, options.stockName);
  await page.goto(`/?recordId=${recordId}`);
  await expect(page.locator('html')).toHaveAttribute('lang', options.uiLanguage === 'en' ? 'en' : 'zh-CN');
  await expect(page.getByText(new RegExp(options.marker)).first()).toBeVisible({ timeout: 15_000 });
  return recordId;
}

test.describe('complete UI i18n acceptance', () => {
  test('[scenario 01] Chinese first login renders the initial-password contract', async ({ page }) => {
    await mockFirstLoginStatus(page);
    await page.goto('/login');
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
    await expect(page.getByRole('heading', { name: '设置初始密码' })).toBeVisible();
    await expect(page.locator('#passwordConfirm')).toBeVisible();
    await expect(page.getByRole('button', { name: '完成设置并登录' })).toBeVisible();
  });

  test('[scenario 02] English first login renders the initial-password contract', async ({ page }) => {
    await mockFirstLoginStatus(page);
    await page.addInitScript((key) => localStorage.setItem(key, 'en'), UI_LANGUAGE_STORAGE_KEY);
    await page.goto('/login');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.getByRole('heading', { name: 'Set initial password' })).toBeVisible();
    await expect(page.locator('#passwordConfirm')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Finish setup and sign in' })).toBeVisible();
  });

  test('[scenario 03] returning-user login errors follow the current UI language', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await page.context().clearCookies();
    await page.waitForURL(/\/login(?:\?|$)/, { timeout: 10_000 }).catch(async () => {
      await page.goto('/login');
    });
    await page.evaluate((key) => localStorage.setItem(key, 'en'), UI_LANGUAGE_STORAGE_KEY);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Admin login' })).toBeVisible();
    await page.locator('#password').fill('definitely-wrong-password');
    await page.getByRole('button', { name: 'Enter workspace' }).click();
    const alert = page.getByRole('alert').filter({ hasText: 'Check the password and try again.' });
    await expect(alert).toContainText('Validation failed');
    await expect(alert).toContainText('Check the password and try again.');
    await expect(page.getByText('The password is incorrect', { exact: true })).toHaveCount(0);
  });

  test('[scenario 04] UI language survives refresh and browser Back/Forward', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
    await switchToEnglish(page);
    expect(await page.evaluate((key) => localStorage.getItem(key), UI_LANGUAGE_STORAGE_KEY)).toBe('en');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await page.getByRole('link', { name: 'Ask' }).click();
    await page.goBack();
    await expect(page.getByRole('link', { name: 'Home' })).toBeVisible();
    await page.goForward();
    await expect(page.getByText(UI_TEXT.en['chat.title'], { exact: true }).first()).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  });

  test('[scenario 05: Home] English chrome and document title', async ({ page }) => {
    await openEnglishRoute(page, '/');
    await expect(page.getByText(UI_TEXT.en['home.analyze'], { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveTitle(new RegExp(UI_TEXT.en['home.pageTitle'], 'i'));
  });

  test('[scenario 05: Chat] English chrome and document title', async ({ page }) => {
    await openEnglishRoute(page, '/chat');
    await expect(page.getByText(UI_TEXT.en['chat.title'], { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveTitle(new RegExp(UI_TEXT.en['chat.pageTitle'], 'i'));
  });

  test('[scenario 05: Screening] English chrome and document title', async ({ page }) => {
    await openEnglishRoute(page, '/screening');
    await expect(page.getByText(SCREENING_TEXT.en.title, { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveTitle(new RegExp(SCREENING_TEXT.en.documentTitle, 'i'));
  });

  test('[scenario 05: Portfolio] English chrome and document title', async ({ page }) => {
    await openEnglishRoute(page, '/portfolio');
    await expect(page.getByText(PORTFOLIO_TEXT.en.title, { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveTitle(new RegExp(PORTFOLIO_TEXT.en.documentTitle, 'i'));
  });

  test('[scenario 05: Decision Signals] English chrome and document title', async ({ page }) => {
    await openEnglishRoute(page, '/decision-signals');
    await expect(page.getByText(UI_TEXT.en['decisionSignals.title'], { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveTitle(new RegExp(UI_TEXT.en['decisionSignals.pageTitle'], 'i'));
  });

  test('[scenario 05: Backtest] English chrome and document title', async ({ page }) => {
    await openEnglishRoute(page, '/backtest');
    await expect(page.getByText(BACKTEST_TEXT.en.runBacktest, { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveTitle(new RegExp(BACKTEST_TEXT.en.documentTitle, 'i'));
  });

  test('[scenario 05: Alerts] English chrome and document title', async ({ page }) => {
    await openEnglishRoute(page, '/alerts');
    await expect(page.getByText(ALERT_PAGE_TEXT.en.title, { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveTitle(new RegExp(ALERT_PAGE_TEXT.en.documentTitle, 'i'));
  });

  test('[scenario 05: Usage] English chrome and document title', async ({ page }) => {
    await openEnglishRoute(page, '/usage');
    await expect(page.getByText(UI_TEXT.en['usage.title'], { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveTitle(new RegExp(UI_TEXT.en['usage.title'], 'i'));
  });

  test('[scenario 05: Settings] English chrome and document title', async ({ page }) => {
    await openEnglishRoute(page, '/settings');
    await expect(page.getByText(UI_TEXT.en['settings.pageTitle'], { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveTitle(new RegExp(UI_TEXT.en['settings.pageTitle'], 'i'));
  });

  test('[scenario 05: Not Found] English chrome and document title', async ({ page }) => {
    await openEnglishRoute(page, '/missing-i18n-route');
    await expect(page.getByText(UI_TEXT.en['notFound.title'], { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveTitle(new RegExp(UI_TEXT.en['notFound.pageTitle'], 'i'));
  });

  test('[scenario 06] Chinese UI renders a Chinese report body', async ({ page }) => {
    await openSeededReport(page, {
      uiLanguage: 'zh',
      stockName: 'E2E Chinese Report',
      marker: REPORT_ZH_MARKER,
    });
    await expect(page.getByRole('button', { name: REPORT_CHROME_TEXT.zh.fullReport })).toBeVisible();
  });

  test('[scenario 07] Chinese UI preserves an English report body', async ({ page }) => {
    await openSeededReport(page, {
      uiLanguage: 'zh',
      stockName: 'E2E English Report',
      marker: REPORT_EN_MARKER,
    });
    await expect(page.getByRole('button', { name: REPORT_CHROME_TEXT.zh.fullReport })).toBeVisible();
  });

  test('[scenario 08] English UI preserves a Chinese report body', async ({ page }) => {
    await openSeededReport(page, {
      uiLanguage: 'en',
      stockName: 'E2E Chinese Report',
      marker: REPORT_ZH_MARKER,
    });
    await expect(page.getByRole('button', { name: REPORT_CHROME_TEXT.en.fullReport })).toBeVisible();
  });

  test('[scenario 09] English UI renders an English report body', async ({ page }) => {
    await openSeededReport(page, {
      uiLanguage: 'en',
      stockName: 'E2E English Report',
      marker: REPORT_EN_MARKER,
    });
    await expect(page.getByRole('button', { name: REPORT_CHROME_TEXT.en.fullReport })).toBeVisible();
  });

  test('[scenario 10] report copy, diagnostics, and provenance chrome follow UI language', async ({ page }) => {
    await openSeededReport(page, {
      uiLanguage: 'zh',
      stockName: 'E2E English Report',
      marker: REPORT_EN_MARKER,
    });
    await expect(page.getByText(REPORT_CHROME_TEXT.zh.traceability, { exact: true })).toBeVisible();
    await expect(page.getByText(REPORT_CHROME_TEXT.zh.eyebrow, { exact: true })).toBeVisible();
    await page.getByRole('button', { name: UI_TEXT.zh['home.fullReport'], exact: true }).click();
    await expect(page.getByRole('button', { name: REPORT_CHROME_TEXT.zh.copyMarkdownSource })).toBeVisible();
    await page.getByRole('button', { name: REPORT_CHROME_TEXT.zh.close, exact: true }).click();
    await expect(page.getByRole('dialog')).toBeHidden();
    // ReportMarkdownDrawer defers the parent close by its 300ms exit duration.
    await page.waitForTimeout(350);

    await switchToEnglish(page);
    await expect(page.getByText(REPORT_CHROME_TEXT.en.traceability, { exact: true })).toBeVisible();
    await expect(page.getByText(REPORT_CHROME_TEXT.en.eyebrow, { exact: true })).toBeVisible();
    await page.getByRole('button', { name: UI_TEXT.en['home.fullReport'], exact: true }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('button', { name: REPORT_CHROME_TEXT.en.copyMarkdownSource })).toBeVisible();
    await expect(page.getByText(new RegExp(REPORT_EN_MARKER)).first()).toBeVisible();
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
