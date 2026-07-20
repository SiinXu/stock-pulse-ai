// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Page } from '@playwright/test';

const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 1280, height: 820 },
  { width: 1024, height: 768 },
  { width: 900, height: 800 },
  { width: 768, height: 900 },
  { width: 767, height: 900 },
  { width: 390, height: 844 },
  { width: 390, height: 667 },
  { width: 320, height: 700 },
] as const;

async function openFixture(page: Page, width: number, height: number, search = '') {
  await page.setViewportSize({ width, height });
  await page.goto(`/e2e/data-table-fixture.html${search}`);
  await expect(page.getByRole('heading', { level: 1, name: 'Tracked decision signals' })).toBeVisible();
}

async function expectNoDocumentOverflow(page: Page, label: string) {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content, `${label}: ${dimensions.content}px content in ${dimensions.viewport}px viewport`)
    .toBeLessThanOrEqual(dimensions.viewport + 1);
}

test.describe('shared DataTable foundation', () => {
  test('keeps sorting controlled with native table semantics', async ({ page }) => {
    await openFixture(page, 1024, 768);
    const table = page.getByRole('table', { name: 'Tracked decision signals' });
    await expect(table).toBeVisible();
    await expect(table.getByRole('columnheader', { name: 'Sort by symbol' })).toHaveAttribute('aria-sort', 'ascending');
    await expect(table.getByRole('rowheader').first()).toHaveText(/AAPL/);

    await page.getByRole('button', { name: 'Sort by last price' }).click();
    await expect(table.getByRole('columnheader', { name: 'Sort by last price' })).toHaveAttribute('aria-sort', 'ascending');
    await expect(table.getByRole('rowheader').first()).toHaveText(/NVDA/);
    const dividerColors = await table.locator('tbody tr:not(:last-child)').evaluateAll((rows) => (
      rows.map((row) => getComputedStyle(row).borderBottomColor)
    ));
    expect(new Set(dividerColors).size).toBe(1);

    await page.getByRole('button', { name: 'Sort by last price' }).click();
    await expect(table.getByRole('columnheader', { name: 'Sort by last price' })).toHaveAttribute('aria-sort', 'descending');
    await expect(table.getByRole('rowheader').first()).toHaveText(/MSFT/);
  });

  test('separates row click and keyboard activation from nested actions', async ({ page }) => {
    await openFixture(page, 1280, 820);
    const aaplRow = page.getByRole('row', { name: 'Open AAPL signal' });
    await aaplRow.getByRole('button', { name: 'Inspect' }).click();
    await expect(page.getByTestId('nested-result')).toHaveText('Inspected AAPL');
    await expect(page.getByTestId('row-result')).toHaveText('No row opened');

    await aaplRow.getByRole('rowheader', { name: /AAPL/ }).click();
    await expect(page.getByTestId('row-result')).toHaveText('Opened AAPL');

    const msftRow = page.getByRole('row', { name: 'Open MSFT signal' });
    await msftRow.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('row-result')).toHaveText('Opened MSFT');
    await msftRow.getByRole('button', { name: 'Inspect' }).focus();
    await page.keyboard.press('Space');
    await expect(page.getByTestId('nested-result')).toHaveText('Inspected MSFT');
    await expect(page.getByTestId('row-result')).toHaveText('Opened MSFT');
  });

  test('renders one authoritative loading, empty, error, or retrying state', async ({ page }) => {
    await openFixture(page, 390, 667, '?state=loading');
    await expect(page.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    await expect(page.getByRole('table')).toHaveCount(0);

    await openFixture(page, 390, 667, '?state=empty');
    await expect(page.getByText('No tracked signals')).toBeVisible();
    await expect(page.getByRole('table')).toHaveCount(0);

    await openFixture(page, 390, 667, '?state=error');
    await expect(page.getByRole('alert')).toContainText('Signals unavailable');
    await page.getByRole('button', { name: 'Retry table' }).click();
    await expect(page.getByRole('table', { name: 'Tracked decision signals' })).toBeVisible();

    await openFixture(page, 390, 667, '?state=retrying');
    await expect(page.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    await expect(page.getByText('Retrying tracked signals')).toBeVisible();
  });

  test('contains horizontal scrolling inside the table at every contract viewport', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const viewport of VIEWPORTS) {
      await openFixture(page, viewport.width, viewport.height);
      await expectNoDocumentOverflow(page, `${viewport.width}x${viewport.height}`);
      const scrollRegion = page.getByRole('region', { name: 'Scrollable tracked decision signals' });
      await scrollRegion.focus();
      await expect(scrollRegion).toBeFocused();
      const dimensions = await scrollRegion.evaluate((element) => ({
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
        left: element.getBoundingClientRect().left,
        right: element.getBoundingClientRect().right,
      }));
      expect(dimensions.left).toBeGreaterThanOrEqual(0);
      expect(dimensions.right).toBeLessThanOrEqual(viewport.width + 1);
      if (viewport.width <= 900) {
        expect(dimensions.scrollWidth).toBeGreaterThan(dimensions.clientWidth);
        const scrollLeft = await scrollRegion.evaluate((element) => {
          element.scrollLeft = element.scrollWidth;
          return element.scrollLeft;
        });
        expect(scrollLeft).toBeGreaterThan(0);
      }
    }

    await page.evaluate(() => localStorage.setItem('theme', 'dark'));
    await page.reload();
    await expect(page.locator('html')).toHaveClass(/(?:^|\s)dark(?:\s|$)/);
    await expectNoDocumentOverflow(page, 'dark 320x700');
  });
});
