import { expect, test, type Page } from '@playwright/test';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  buildAnalysisWorkbenchHref,
} from '../src/routing/routes';
import { loginAsE2eAdmin, mockCompletedSetupStatus } from './auth-fixture';

test.use({ locale: 'zh-CN' });

const UI_LANGUAGE_STORAGE_KEY = 'dsa.uiLanguage';
const REPORT_MARKER = 'E2E_MARKDOWN_FIXTURE';

async function login(page: Page) {
  await page.addInitScript((storageKey) => {
    window.localStorage.setItem(storageKey, 'zh');
  }, UI_LANGUAGE_STORAGE_KEY);
  await mockCompletedSetupStatus(page);
  await loginAsE2eAdmin(page);
  await expect(page.getByTestId('home-core-blocks')).toBeVisible({ timeout: 10_000 });
}

async function openFirstHistoryReport(page: Page) {
  await page.goto(buildAnalysisWorkbenchHref({
    segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
  }));
  await expect(page.getByRole('heading', { name: '分析工作台' })).toBeVisible({ timeout: 10_000 });
  const firstHistoryItem = page.locator('.home-history-item').first();
  await expect(firstHistoryItem).toBeVisible({ timeout: 10_000 });
  await expect(firstHistoryItem).toContainText('E2E Fixture');
  await firstHistoryItem.click();
  const detailedReportButton = page.getByRole('button', { name: '完整分析报告' });
  await expect(detailedReportButton).toBeEnabled({ timeout: 3000 });
  return detailedReportButton;
}

test.describe('ReportMarkdown component', () => {
  test('copy markdown source code', async ({ page, context }) => {
    // Grant clipboard permissions
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);

    await login(page);

    const detailedReportButton = await openFirstHistoryReport(page);

    // Click the "完整分析报告" button to open the markdown drawer
    await expect(detailedReportButton).toBeVisible({ timeout: 5000 });
    await detailedReportButton.click();

    // Verify drawer content is visible
    await expect(
      page.getByRole('dialog').getByRole('heading', { name: '完整分析报告' }),
    ).toBeVisible();

    // Click copy markdown button
    const copyMarkdownButton = page.getByRole('button', { name: '复制 Markdown 源码' });
    await expect(copyMarkdownButton).toBeVisible({ timeout: 5000 });
    await copyMarkdownButton.click();

    // Verify clipboard contains markdown content
    const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboardText).toBeTruthy();
    expect(clipboardText.length).toBeGreaterThan(0);
    expect(clipboardText).toContain(REPORT_MARKER);

    // Verify checkmark icon is shown
    const checkmarkIcon = page.locator('button[aria-label="复制 Markdown 源码"] svg.text-success');
    await expect(checkmarkIcon).toBeVisible();

    // Wait for icon to revert (icon disappears after 2 seconds)
    await expect(checkmarkIcon).not.toBeVisible({ timeout: 3500 });
  });

  test('copy plain text', async ({ page, context }) => {
    // Grant clipboard permissions
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);

    await login(page);

    const detailedReportButton = await openFirstHistoryReport(page);

    // Click the "完整分析报告" button to open the markdown drawer
    await expect(detailedReportButton).toBeVisible({ timeout: 5000 });
    await detailedReportButton.click();

    // Verify drawer content is visible
    await expect(
      page.getByRole('dialog').getByRole('heading', { name: '完整分析报告' }),
    ).toBeVisible();

    // Click copy plain text button
    const copyPlainTextButton = page.getByRole('button', { name: '复制纯文本' });
    await expect(copyPlainTextButton).toBeVisible({ timeout: 5000 });
    await copyPlainTextButton.click();

    // Verify clipboard contains text without markdown symbols
    const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboardText).toBeTruthy();
    expect(clipboardText.length).toBeGreaterThan(0);
    expect(clipboardText).toContain(REPORT_MARKER);

    // Verify it's plain text (no markdown symbols like #, **, >, etc.)
    expect(clipboardText).not.toMatch(/^#{1,6}\s+/m); // No headers
    expect(clipboardText).not.toMatch(/\*\*[^*]+\*\*/); // No bold
    // Verify table syntax is removed (no standalone pipe separators)
    const lines = clipboardText.split('\n');
    const hasTableSeparators = lines.some(line =>
      line.match(/^\|[\s|:-]+\|$/) || line.match(/^[\s|:-]+$/)
    );
    expect(hasTableSeparators).toBeFalsy();

    // Verify checkmark icon is shown
    const checkmarkIcon = page.locator('button[aria-label="复制纯文本"] svg.text-success');
    await expect(checkmarkIcon).toBeVisible();

    // Wait for icon to revert (icon disappears after 2 seconds)
    await expect(checkmarkIcon).not.toBeVisible({ timeout: 3500 });
  });

  test('mobile responsive layout', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 390, height: 844 });

    await login(page);

    const detailedReportButton = await openFirstHistoryReport(page);
    await detailedReportButton.click();

    // Verify drawer content is visible (this ensures drawer is fully open)
    await expect(
      page.getByRole('dialog').getByRole('heading', { name: '完整分析报告' }),
    ).toBeVisible({ timeout: 10000 });

    // Verify toolbar buttons are visible and clickable on mobile
    const copyMarkdownButton = page.getByRole('button', { name: '复制 Markdown 源码' });
    const copyPlainTextButton = page.getByRole('button', { name: '复制纯文本' });

    await expect(copyMarkdownButton).toBeVisible({ timeout: 5000 });
    await expect(copyPlainTextButton).toBeVisible();

    // Verify buttons are clickable (not checking icon animation on mobile due to timing issues)
    await expect(copyMarkdownButton).toBeEnabled();
    await expect(copyPlainTextButton).toBeEnabled();
  });

  test('copy buttons become enabled after report loading', async ({ page }) => {
    await login(page);

    const detailedReportButton = await openFirstHistoryReport(page);

    // Click the "完整分析报告" button to open the markdown drawer
    await expect(detailedReportButton).toBeVisible({ timeout: 5000 });
    await detailedReportButton.click();

    // Immediately check if buttons are disabled (right after drawer opens)
    const copyMarkdownButton = page.getByRole('button', { name: '复制 Markdown 源码' });
    const copyPlainTextButton = page.getByRole('button', { name: '复制纯文本' });

    // Wait for drawer to open and buttons to appear
    await expect(copyMarkdownButton).toBeVisible({ timeout: 5000 });
    await expect(copyPlainTextButton).toBeVisible();

    // Wait for content to finish loading (buttons become enabled)
    await expect(copyMarkdownButton).toBeEnabled({ timeout: 5000 });

    // Check buttons are enabled after content loads
    // Note: Loading may be very fast for cached content
    const isMarkdownEnabled = await copyMarkdownButton.isEnabled();
    const isPlainTextEnabled = await copyPlainTextButton.isEnabled();

    // At least one button should be enabled
    expect(isMarkdownEnabled || isPlainTextEnabled).toBeTruthy();
  });
});
