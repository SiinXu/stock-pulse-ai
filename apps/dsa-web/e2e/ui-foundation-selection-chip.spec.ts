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

async function openFixture(page: Page, width: number, height: number) {
  await page.setViewportSize({ width, height });
  await page.goto('/e2e/selection-chip-fixture.html');
  await expect(page.getByRole('heading', { level: 1, name: 'Candidate stocks' })).toBeVisible();
}

async function expectNoDocumentOverflow(page: Page, label: string) {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content, `${label}: ${dimensions.content}px content in ${dimensions.viewport}px viewport`)
    .toBeLessThanOrEqual(dimensions.viewport + 1);
}

test.describe('shared SelectionChip foundation', () => {
  test('exposes persistent selection and one-shot command semantics', async ({ page }) => {
    await openFixture(page, 1024, 768);
    const aapl = page.getByRole('button', { name: /AAPL Apple Incorporated/ });
    const msft = page.getByRole('button', { name: /MSFT Microsoft Corporation/ });
    const brkb = page.getByRole('button', { name: /BRK\.B Berkshire Hathaway/ });
    const oneShot = page.getByRole('button', { name: 'Open market leader' });

    await expect(aapl).toHaveAttribute('aria-pressed', 'true');
    await expect(msft).toHaveAttribute('aria-pressed', 'false');
    await expect(oneShot).not.toHaveAttribute('aria-pressed');

    await msft.click();
    await expect(msft).toHaveAttribute('aria-pressed', 'true');
    await expect(aapl).toHaveAttribute('aria-pressed', 'false');
    await expect(page.getByTestId('selection-result')).toHaveText('Selected MSFT');

    await brkb.focus();
    await page.keyboard.press('Space');
    await expect(brkb).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByTestId('selection-result')).toHaveText('Selected BRK.B');

    await oneShot.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('selection-result')).toHaveText('Opened market leader');
    await expect(brkb).toHaveAttribute('aria-pressed', 'true');
  });

  test('grows for long labels without escaping any contract viewport', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const viewport of VIEWPORTS) {
      await openFixture(page, viewport.width, viewport.height);
      await expectNoDocumentOverflow(page, `${viewport.width}x${viewport.height}`);
      const longCandidate = page.getByRole('button', { name: /BRK\.B Berkshire Hathaway/ });
      const bounds = await longCandidate.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width + 1);
      if (viewport.width === 320) expect(bounds!.height).toBeGreaterThan(36);
    }
  });

  test('retains focus, disabled, loading, and both theme states', async ({ page }) => {
    await openFixture(page, 390, 667);
    const disabled = page.getByRole('button', { name: /PRIVATE Unavailable candidate/ });
    await expect(disabled).toBeDisabled();
    const loading = page.getByRole('button', { name: /SYNCING Refreshing candidate data/ });
    await expect(loading).toBeDisabled();
    await expect(loading).toHaveAttribute('aria-busy', 'true');
    await expect(loading.locator('[data-indicator="loading"]')).toBeVisible();

    await page.evaluate(() => localStorage.setItem('theme', 'light'));
    await page.reload();
    await expect(page.locator('html')).toHaveClass(/(?:^|\s)light(?:\s|$)/);
    await expectNoDocumentOverflow(page, 'light 390x667');

    const msft = page.getByRole('button', { name: /MSFT Microsoft Corporation/ });
    await msft.focus();
    await expect(msft).toBeFocused();

    await page.evaluate(() => localStorage.setItem('theme', 'dark'));
    await page.reload();
    await expect(page.locator('html')).toHaveClass(/(?:^|\s)dark(?:\s|$)/);
    await expectNoDocumentOverflow(page, 'dark 390x667');
  });
});
