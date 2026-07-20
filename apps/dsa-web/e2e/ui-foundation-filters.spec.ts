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
  await page.goto(`/e2e/filter-pattern-fixture.html${search}`);
  await expect(page.getByRole('heading', { level: 1, name: 'Review decision signals' })).toBeVisible();
}

async function expectNoHorizontalOverflow(page: Page, label: string): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content, `${label}: ${dimensions.content}px content in ${dimensions.viewport}px viewport`)
    .toBeLessThanOrEqual(dimensions.viewport + 1);
}

test.describe('shared Filter and Query foundation', () => {
  test('keeps draft changes local and restores applied filters with browser navigation', async ({ page }) => {
    await openFixture(page, 390, 667, '?market=us&page=3&source=report');

    await expect(page.getByRole('button', { name: 'Remove Market filter' })).toBeVisible();
    await expect(page.getByTestId('result-summary')).toHaveText('20 results');
    await page.getByRole('textbox', { name: 'Stock code' }).fill('aapl');
    await expect(page).toHaveURL(/market=us&page=3&source=report/);

    await page.getByRole('button', { name: 'Apply filters' }).click();
    await expect(page).toHaveURL(/market=us/);
    await expect(page).toHaveURL(/source=report/);
    await expect(page).toHaveURL(/stock=AAPL/);
    await expect(page).not.toHaveURL(/page=3/);
    await expect(page.getByRole('button', { name: 'Remove Stock filter' })).toBeVisible();
    await expect(page.getByTestId('result-summary')).toHaveText('16 results for AAPL');

    const advancedTrigger = page.getByRole('button', { name: /^More filters/ });
    await advancedTrigger.click();
    const sheet = page.getByRole('dialog', { name: 'More filters' });
    await expect(sheet).toHaveAttribute('aria-modal', 'true');
    const footer = sheet.locator('[data-overlay-slot="footer"]');
    const footerBox = await footer.boundingBox();
    expect(footerBox).not.toBeNull();
    expect(footerBox!.y + footerBox!.height).toBeLessThanOrEqual(667);

    await sheet.getByRole('textbox', { name: 'Status' }).fill('open');
    await sheet.getByRole('button', { name: 'View 12 results' }).click();
    await expect(sheet).toHaveCount(0);
    await expect(page).toHaveURL(/status=open/);
    await expect(page.getByTestId('result-summary')).toHaveText('12 results for AAPL');
    await expect(advancedTrigger).toBeFocused();

    await page.goBack();
    await expect(page).not.toHaveURL(/status=open/);
    await expect(page.getByRole('button', { name: 'Remove Status filter' })).toHaveCount(0);
    await expect(page.getByTestId('result-summary')).toHaveText('16 results for AAPL');

    await page.goForward();
    await expect(page).toHaveURL(/status=open/);
    await expect(page.getByRole('button', { name: 'Remove Status filter' })).toBeVisible();
    await expectNoHorizontalOverflow(page, '390x667 applied filters');
  });

  test('uses a focused non-modal Popover at 768px and a modal Sheet below it', async ({ page }) => {
    await openFixture(page, 768, 900, '?source=report');
    const desktopTrigger = page.getByRole('button', { name: 'More filters' });
    await desktopTrigger.click();
    let advanced = page.getByRole('dialog', { name: 'More filters' });
    await expect(advanced).not.toHaveAttribute('aria-modal');
    await expect(page.locator('[data-overlay-root="sheet"]')).toHaveCount(0);
    await expect(advanced.getByRole('textbox', { name: 'Market' })).toBeFocused();

    await page.setViewportSize({ width: 767, height: 900 });
    await expect(advanced).toHaveCount(0);
    await expect(desktopTrigger).toBeFocused();
    const mobileTrigger = page.getByRole('button', { name: 'More filters' });
    await mobileTrigger.click();
    advanced = page.getByRole('dialog', { name: 'More filters' });
    await expect(advanced).toHaveAttribute('aria-modal', 'true');
    await expect(page.locator('[data-overlay-root="sheet"]')).toHaveCount(1);
  });

  test('stays within all contract viewports in light, dark, and reduced-motion modes', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const viewport of VIEWPORTS) {
      await openFixture(page, viewport.width, viewport.height, '?market=us&stock=AAPL');
      await expectNoHorizontalOverflow(page, `${viewport.width}x${viewport.height}`);
      await page.getByRole('button', { name: 'More filters, 1 active' }).click();
      const dialog = page.getByRole('dialog', { name: 'More filters' });
      await expect(dialog).toBeVisible();
      const box = await dialog.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 1);
      expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height + 1);
      await page.keyboard.press('Escape');
    }

    await page.evaluate(() => localStorage.setItem('theme', 'dark'));
    await page.reload();
    await expect(page.locator('html')).toHaveClass(/(?:^|\s)dark(?:\s|$)/);
    await expectNoHorizontalOverflow(page, 'dark 320x700');
  });
});
