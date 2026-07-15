import {
  expect,
  test,
  type Locator,
  type Page,
  type Route,
  type TestInfo,
} from '@playwright/test';
import { UI_TEXT } from '../src/i18n/uiText';
import { ALERT_PAGE_TEXT } from '../src/locales/alerts';
import { BACKTEST_TEXT } from '../src/locales/backtest';
import { PORTFOLIO_TEXT } from '../src/locales/portfolio';
import { SCREENING_TEXT } from '../src/locales/screening';
import { loginAsE2eAdmin } from './auth-fixture';

test.use({
  locale: 'zh-CN',
  hasTouch: true,
});

const DESKTOP_VIEWPORT = { width: 1280, height: 900 };
const MOBILE_VIEWPORT = { width: 390, height: 844 };

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function fulfillRealResponseAfter(route: Route, milliseconds: number): Promise<void> {
  const response = await route.fetch();
  await sleep(milliseconds);
  await route.fulfill({ response });
}

async function expectElementWithinViewport(locator: Locator, viewportWidth: number): Promise<void> {
  await expect(locator).toBeVisible({ timeout: 15_000 });
  await locator.scrollIntoViewIfNeeded();
  await expect(locator).toBeInViewport();
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(-1);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewportWidth + 1);
}

async function expectPageFitsViewport(
  page: Page,
  critical: Locator | Locator[],
  viewportWidth: number,
): Promise<void> {
  const criticalElements = Array.isArray(critical) ? critical : [critical];
  for (const element of criticalElements) {
    await expectElementWithinViewport(element, viewportWidth);
  }
  const widths = await page.evaluate(() => {
    const root = document.documentElement;
    const body = document.body;
    return {
      innerWidth: window.innerWidth,
      rootClientWidth: root.clientWidth,
      rootScrollWidth: root.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
    };
  });
  expect(widths.innerWidth).toBe(viewportWidth);
  expect(widths.rootClientWidth).toBe(viewportWidth);
  expect(widths.rootScrollWidth).toBeLessThanOrEqual(viewportWidth + 1);
  expect(widths.bodyScrollWidth).toBeLessThanOrEqual(viewportWidth + 1);
}

async function attachPassScreenshot(
  page: Page,
  testInfo: TestInfo,
  name: string,
  options?: { fullPage?: boolean },
): Promise<void> {
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({
    path,
    fullPage: options?.fullPage ?? false,
    animations: 'disabled',
  });
  await testInfo.attach(name, { path, contentType: 'image/png' });
}

async function selectTheme(page: Page, theme: '浅色' | '深色'): Promise<void> {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  const trigger = page.getByRole('button', { name: '切换主题' }).first();
  await expect(trigger).toBeVisible();
  await trigger.click();
  await page.getByRole('menuitemradio', { name: theme, exact: true }).click();
  if (theme === '深色') {
    await expect(page.locator('html')).toHaveClass(/dark/);
  } else {
    await expect(page.locator('html')).not.toHaveClass(/dark/);
  }
}

async function expectReadableText(locator: Locator): Promise<void> {
  await expect(locator).toBeVisible({ timeout: 15_000 });
  const contrast = await locator.evaluate((element) => {
    const parseColor = (value: string): [number, number, number, number] | null => {
      const match = value.match(/rgba?\(([^)]+)\)/);
      if (!match) return null;
      const parts = match[1].split(/[\s,/]+/).filter(Boolean).map(Number);
      if (parts.length < 3 || parts.slice(0, 3).some(Number.isNaN)) return null;
      return [parts[0], parts[1], parts[2], Number.isFinite(parts[3]) ? parts[3] : 1];
    };
    const luminance = ([red, green, blue]: [number, number, number]) => {
      const channels = [red, green, blue].map((channel) => {
        const normalized = channel / 255;
        return normalized <= 0.03928
          ? normalized / 12.92
          : ((normalized + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    };

    const foreground = parseColor(getComputedStyle(element).color);
    let background: [number, number, number, number] | null = null;
    let current: Element | null = element;
    while (current && !background) {
      const candidate = parseColor(getComputedStyle(current).backgroundColor);
      if (candidate && candidate[3] >= 0.99) background = candidate;
      current = current.parentElement;
    }
    if (!foreground || !background) return 0;
    const foregroundLuminance = luminance(foreground.slice(0, 3) as [number, number, number]);
    const backgroundLuminance = luminance(background.slice(0, 3) as [number, number, number]);
    const lighter = Math.max(foregroundLuminance, backgroundLuminance);
    const darker = Math.min(foregroundLuminance, backgroundLuminance);
    return (lighter + 0.05) / (darker + 0.05);
  });
  expect(contrast).toBeGreaterThanOrEqual(4.5);
}

test.describe('semantic interaction resilience', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsE2eAdmin(page);
  });

  test('Decision Signals keeps the latest stock scope after out-of-order requests', async ({ page }, testInfo) => {
    await page.setViewportSize(DESKTOP_VIEWPORT);
    let slowStarted = 0;
    let slowCompleted = 0;
    let fastStarted = 0;
    let fastCompleted = 0;

    await page.route('**/api/v1/decision-signals**', async (route) => {
      const url = new URL(route.request().url());
      const latestPrefix = '/api/v1/decision-signals/latest/';
      const stockCode = url.pathname.startsWith(latestPrefix)
        ? decodeURIComponent(url.pathname.slice(latestPrefix.length))
        : url.pathname === '/api/v1/decision-signals'
          ? url.searchParams.get('stock_code')
          : null;
      if (stockCode === 'AAPL') {
        slowStarted += 1;
        await fulfillRealResponseAfter(route, 2_000);
        slowCompleted += 1;
        return;
      }
      if (stockCode === 'MSFT') {
        fastStarted += 1;
        await fulfillRealResponseAfter(route, 40);
        fastCompleted += 1;
        return;
      }
      await route.continue();
    });

    await page.goto('/decision-signals?stock=AAPL');
    await expect(page.getByRole('heading', { name: UI_TEXT.zh['decisionSignals.title'], exact: true })).toBeVisible();
    await expect.poll(() => slowStarted).toBeGreaterThanOrEqual(2);

    const currentStockButton = page.getByRole('button', { name: '当前查看：AAPL' });
    await expect(currentStockButton).toBeVisible();
    await currentStockButton.click();
    const dialog = page.getByRole('dialog', { name: UI_TEXT.zh['decisionSignals.stockContextTitle'] });
    await expect(dialog).toBeVisible();
    const stockInput = dialog.getByLabel(UI_TEXT.zh['decisionSignals.stockContextInput']);
    await stockInput.fill('MSFT');
    await expect(stockInput).toHaveValue('MSFT');
    await dialog.getByRole('button', { name: UI_TEXT.zh['decisionSignals.stockContextApply'] }).click();
    await expect(page).toHaveURL(/(?:\?|&)stock=MSFT(?:&|$)/);

    await expect.poll(() => fastStarted).toBeGreaterThanOrEqual(2);
    await expect.poll(() => fastCompleted).toBeGreaterThanOrEqual(2);
    await expect(page.getByText('当前股票 · MSFT', { exact: true })).toHaveCount(2);
    await expect.poll(() => slowCompleted).toBeGreaterThanOrEqual(2);
    await expect(page.getByText('当前股票 · MSFT', { exact: true })).toHaveCount(2);
    await expect(page.getByText('当前股票 · AAPL', { exact: true })).toHaveCount(0);
    await expect(page).toHaveURL(/(?:\?|&)stock=MSFT(?:&|$)/);
    await attachPassScreenshot(page, testInfo, 'decision-signals-desktop-latest-scope');
  });

  test('Backtest keeps results and performance on the newest filter request', async ({ page }) => {
    let slowStarted = 0;
    let slowCompleted = 0;
    let fastStarted = 0;
    let fastCompleted = 0;
    await page.route('**/api/v1/backtest/**', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.continue();
        return;
      }
      const url = new URL(route.request().url());
      const stockCode = url.pathname.startsWith('/api/v1/backtest/performance/')
        ? decodeURIComponent(url.pathname.slice('/api/v1/backtest/performance/'.length))
        : url.searchParams.get('code');
      const windowDays = url.searchParams.get('eval_window_days');
      if (stockCode === 'AAPL' || windowDays === '10') {
        slowStarted += 1;
        await fulfillRealResponseAfter(route, 700);
        slowCompleted += 1;
        return;
      }
      if (stockCode === 'MSFT' || windowDays === '1') {
        fastStarted += 1;
        await fulfillRealResponseAfter(route, 40);
        fastCompleted += 1;
        return;
      }
      await route.continue();
    });

    await page.goto('/backtest?window=2');
    const codeInput = page.getByPlaceholder(BACKTEST_TEXT.zh.codePlaceholder);
    const windowInput = page.getByPlaceholder('10');
    const fromInput = page.getByLabel(BACKTEST_TEXT.zh.startDateAria);
    const toInput = page.getByLabel(BACKTEST_TEXT.zh.endDateAria);
    await expect(codeInput).toBeVisible();
    await expect(page.getByRole('button', { name: BACKTEST_TEXT.zh.filter })).toBeEnabled();

    await codeInput.fill('AAPL');
    await windowInput.fill('10');
    await fromInput.fill('2026-03-31');
    await toInput.fill('2026-03-01');
    await codeInput.press('Enter');
    await expect.poll(() => slowStarted).toBeGreaterThanOrEqual(2);

    await codeInput.fill('MSFT');
    await windowInput.fill('1');
    await fromInput.fill('');
    await toInput.fill('');
    await codeInput.press('Enter');

    await expect.poll(() => fastStarted).toBeGreaterThanOrEqual(3);
    await expect.poll(() => fastCompleted).toBeGreaterThanOrEqual(3);
    await expect.poll(() => slowCompleted).toBeGreaterThanOrEqual(2);
    await expect(page.getByText(BACKTEST_TEXT.zh.noResultsTitle)).toBeVisible();
    await expect(page.getByText(BACKTEST_TEXT.zh.noMetricsTitle)).toBeVisible();
    await expect(page.getByText('AAPL', { exact: true })).toHaveCount(0);
    await expect(codeInput).toHaveValue('MSFT');
    await expect(windowInput).toHaveValue('1');
    await expect(page).toHaveURL(/(?:\?|&)code=MSFT(?:&|$)/);
    await expect(page).toHaveURL(/(?:\?|&)window=1(?:&|$)/);
  });

  test('Escape closes only the top overlay and restores focus in stack order', async ({ page }, testInfo) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    const openNavigation = page.getByRole('button', { name: UI_TEXT.zh['layout.openNav'] });
    await openNavigation.click();
    const navigationRoot = page.locator('[data-overlay-root="drawer"]');
    const navigationDialog = page.getByRole('dialog', { name: UI_TEXT.zh['layout.navMenu'] });
    await expect(navigationDialog).toBeVisible();

    const logoutButton = navigationDialog.getByRole('button', { name: UI_TEXT.zh['layout.logout'] });
    await logoutButton.click();
    const confirmation = page.getByRole('dialog', { name: UI_TEXT.zh['layout.logoutTitle'] });
    await expect(confirmation).toBeVisible();
    await expect(navigationRoot).toBeVisible();
    await attachPassScreenshot(page, testInfo, 'overlay-stack-390');

    await page.keyboard.press('Escape');
    await expect(confirmation).not.toBeVisible();
    await expect(navigationDialog).toBeVisible();
    await expect(logoutButton).toBeFocused();

    await page.keyboard.press('Escape');
    await expect(navigationRoot).not.toBeVisible();
    await expect(openNavigation).toBeFocused();
  });

  test('Home mobile history drawer supports keyboard and touch dismissal', async ({ page }, testInfo) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto('/');
    const trigger = page.getByRole('button', { name: UI_TEXT.zh['home.historyButton'], exact: true });
    await trigger.focus();
    await trigger.press('Enter');
    let dialog = page.getByRole('dialog', { name: UI_TEXT.zh['home.historyButton'] });
    await expect(dialog).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();

    await trigger.tap();
    dialog = page.getByRole('dialog', { name: UI_TEXT.zh['home.historyButton'] });
    await expect(dialog).toBeVisible();
    await attachPassScreenshot(page, testInfo, 'home-history-drawer-390');
    await dialog.getByRole('button', { name: UI_TEXT.zh['common.closeDrawer'] }).tap();
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
  });

  test('Chat mobile conversation drawer supports keyboard and touch dismissal', async ({ page }, testInfo) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto('/chat');
    await expect(page.getByTestId('chat-workspace')).toBeVisible();
    const trigger = page.getByRole('button', { name: UI_TEXT.zh['chat.history'], exact: true });
    await trigger.focus();
    await trigger.press('Enter');
    let dialog = page.getByRole('dialog', { name: UI_TEXT.zh['chat.history'] });
    await expect(dialog).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();

    await trigger.tap();
    dialog = page.getByRole('dialog', { name: UI_TEXT.zh['chat.history'] });
    await expect(dialog).toBeVisible();
    await attachPassScreenshot(page, testInfo, 'chat-conversation-drawer-390');
    await dialog.getByRole('button', { name: UI_TEXT.zh['common.closeDrawer'] }).tap();
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
  });

  test('Home primary analysis controls remain reachable at 320px', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto('/');
    const stockInput = page.getByPlaceholder(UI_TEXT.zh['home.placeholder']);
    const historyButton = page.getByRole('button', { name: UI_TEXT.zh['home.historyButton'], exact: true });
    const marketReviewButton = page.getByRole('button', { name: UI_TEXT.zh['home.marketReview'], exact: true });
    const analyzeButton = page.getByRole('button', { name: UI_TEXT.zh['home.analyze'], exact: true });
    await stockInput.fill('AAPL');
    await expect(analyzeButton).toBeEnabled();
    await expectElementWithinViewport(historyButton, 320);
    await expectElementWithinViewport(stockInput, 320);
    await expectElementWithinViewport(marketReviewButton, 320);
    await expectElementWithinViewport(analyzeButton, 320);
    await expectPageFitsViewport(page, stockInput, 320);
    await attachPassScreenshot(page, testInfo, 'home-primary-controls-320', { fullPage: true });
  });

  test('Home fits a 390px viewport without clipping its primary input', async ({ page }, testInfo) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto('/');
    await expectPageFitsViewport(page, [
      page.getByPlaceholder(UI_TEXT.zh['home.placeholder']),
      page.getByRole('button', { name: UI_TEXT.zh['home.historyButton'], exact: true }),
      page.getByRole('button', { name: UI_TEXT.zh['home.marketReview'], exact: true }),
      page.getByRole('button', { name: UI_TEXT.zh['home.analyze'], exact: true }),
    ], 390);
    await attachPassScreenshot(page, testInfo, 'home-primary-input-390');
  });

  test('Chat fits a 390px viewport without clipping the composer', async ({ page }, testInfo) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto('/chat');
    await expectPageFitsViewport(page, [
      page.getByPlaceholder(/分析 600519/),
      page.getByRole('button', { name: UI_TEXT.zh['chat.history'], exact: true }),
      page.getByRole('button', { name: UI_TEXT.zh['chat.send'], exact: true }),
    ], 390);
    await attachPassScreenshot(page, testInfo, 'chat-critical-actions-390');
  });

  test('Screening fits a 390px viewport without clipping its critical actions', async ({ page }, testInfo) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto('/screening');
    await expectPageFitsViewport(page, [
      page.getByRole('heading', { name: SCREENING_TEXT.zh.title }),
      page.getByRole('button', { name: SCREENING_TEXT.zh.run }),
    ], 390);
    await attachPassScreenshot(page, testInfo, 'screening-critical-actions-390');
  });

  test('Portfolio fits a 390px viewport without clipping its critical actions', async ({ page }, testInfo) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto('/portfolio');
    await expectPageFitsViewport(page, [
      page.getByRole('heading', { name: PORTFOLIO_TEXT.zh.title }),
      page.getByRole('button', { name: PORTFOLIO_TEXT.zh.addAccount }).first(),
      page.getByRole('button', { name: PORTFOLIO_TEXT.zh.csvImport }).first(),
    ], 390);
    await attachPassScreenshot(page, testInfo, 'portfolio-critical-actions-390');
  });

  test('Decision Signals fits a 390px viewport without clipping its critical actions', async ({ page }, testInfo) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto('/decision-signals');
    await expectPageFitsViewport(page, [
      page.getByRole('heading', { name: UI_TEXT.zh['decisionSignals.title'], exact: true }),
      page.getByRole('button', { name: /^(当前股票$|当前查看：)/ }),
      page.getByRole('button', { name: UI_TEXT.zh['decisionSignals.filter'], exact: true }),
    ], 390);
    await attachPassScreenshot(page, testInfo, 'decision-signals-critical-actions-390');
  });

  test('Backtest fits a 390px viewport without clipping its critical actions', async ({ page }, testInfo) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto('/backtest');
    await expectPageFitsViewport(page, [
      page.getByRole('button', { name: BACKTEST_TEXT.zh.filter }),
      page.getByRole('button', { name: BACKTEST_TEXT.zh.runBacktest }),
    ], 390);
    await attachPassScreenshot(page, testInfo, 'backtest-critical-actions-390');
  });

  test('Alerts fits a 390px viewport without clipping its critical actions', async ({ page }, testInfo) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto('/alerts');
    await expectPageFitsViewport(page, [
      page.getByRole('heading', { name: ALERT_PAGE_TEXT.zh.title }),
      page.getByRole('button', { name: ALERT_PAGE_TEXT.zh.createRule }),
    ], 390);
    await attachPassScreenshot(page, testInfo, 'alerts-critical-actions-390');
  });

  test('Usage fits a 390px viewport without clipping its critical actions', async ({ page }, testInfo) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto('/usage');
    await expectPageFitsViewport(page, [
      page.getByRole('heading', { name: UI_TEXT.zh['usage.title'] }),
      page.getByRole('button', { name: UI_TEXT.zh['usage.refresh'] }),
    ], 390);
    await attachPassScreenshot(page, testInfo, 'usage-critical-actions-390');
  });

  test('Settings fits a 390px viewport without clipping its critical actions', async ({ page }, testInfo) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto('/settings');
    await expectPageFitsViewport(page, [
      page.getByRole('heading', { name: UI_TEXT.zh['settings.pageTitle'] }),
      page.getByRole('combobox', { name: UI_TEXT.zh['settings.categoryNavTitle'] }),
    ], 390);
    await attachPassScreenshot(page, testInfo, 'settings-critical-actions-390');
  });

  test('Not Found fits a 390px viewport without clipping its recovery action', async ({ page }, testInfo) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto('/missing-semantic-route');
    await expectPageFitsViewport(page, [
      page.getByRole('heading', { name: UI_TEXT.zh['notFound.title'] }),
      page.getByRole('button', { name: UI_TEXT.zh['notFound.backHome'] }),
    ], 390);
    await attachPassScreenshot(page, testInfo, 'not-found-recovery-390');
  });

  test('Light theme keeps critical page text readable', async ({ page }, testInfo) => {
    await selectTheme(page, '浅色');
    await page.goto('/decision-signals');
    await expectReadableText(page.getByRole('heading', { name: UI_TEXT.zh['decisionSignals.title'], exact: true }));
    await page.goto('/settings');
    await expectReadableText(page.getByRole('heading', { name: UI_TEXT.zh['settings.pageTitle'] }));
    await page.goto('/');
    const input = page.getByPlaceholder(UI_TEXT.zh['home.placeholder']);
    await input.fill('AAPL');
    await expectReadableText(input);
    await expect(page.locator('html')).not.toHaveClass(/dark/);
    await attachPassScreenshot(page, testInfo, 'home-light-theme-desktop');
  });

  test('Dark theme keeps critical page text readable', async ({ page }, testInfo) => {
    await selectTheme(page, '深色');
    await page.goto('/decision-signals');
    await expectReadableText(page.getByRole('heading', { name: UI_TEXT.zh['decisionSignals.title'], exact: true }));
    await page.goto('/settings');
    await expectReadableText(page.getByRole('heading', { name: UI_TEXT.zh['settings.pageTitle'] }));
    await page.goto('/');
    const input = page.getByPlaceholder(UI_TEXT.zh['home.placeholder']);
    await input.fill('AAPL');
    await expectReadableText(input);
    await expect(page.locator('html')).toHaveClass(/dark/);
    await attachPassScreenshot(page, testInfo, 'home-dark-theme-desktop');
  });
});
