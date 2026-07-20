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

async function openFixture(page: Page, width: number, height: number): Promise<void> {
  await page.setViewportSize({ width, height });
  await page.goto('/e2e/surface-contract-fixture.html');
  await expect(page.getByRole('heading', { level: 1, name: 'Token usage' })).toBeVisible();
}

async function expectNoDocumentOverflow(page: Page, label: string): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content, `${label}: ${dimensions.content}px content in ${dimensions.viewport}px viewport`)
    .toBeLessThanOrEqual(dimensions.viewport + 1);
}

async function themeTokenStyles(page: Page): Promise<{
  fill: string;
  divider: string;
  ring: string;
}> {
  return page.evaluate(() => {
    const fill = getComputedStyle(document.querySelector('[data-testid="semantic-fill"]')!);
    const ring = getComputedStyle(document.querySelector('[data-testid="semantic-ring"]')!);
    return {
      fill: fill.backgroundColor,
      divider: fill.borderBottomColor,
      ring: ring.boxShadow,
    };
  });
}

async function surfaceBoundaries(page: Page) {
  return page.evaluate(() => Object.fromEntries(
    ['canvas', 'section', 'interactive', 'overlay'].map((level) => {
      const style = getComputedStyle(document.querySelector(`[data-testid="surface-${level}"]`)!);
      return [level, {
        backgroundColor: style.backgroundColor,
        borderTopWidth: style.borderTopWidth,
        borderRadius: style.borderRadius,
        boxShadow: style.boxShadow,
      }];
    }),
  ));
}

function expectSurfaceBoundaryContract(boundaries: Awaited<ReturnType<typeof surfaceBoundaries>>): void {
  expect(boundaries.canvas).toEqual({
    backgroundColor: 'rgba(0, 0, 0, 0)',
    borderTopWidth: '0px',
    borderRadius: '0px',
    boxShadow: 'none',
  });
  expect(boundaries.section.backgroundColor).not.toBe('rgba(0, 0, 0, 0)');
  expect(boundaries.section.borderTopWidth).toBe('0px');
  expect(boundaries.section.boxShadow).toBe('none');
  expect(boundaries.interactive.borderTopWidth).toBe('1px');
  expect(boundaries.interactive.boxShadow).toBe('none');
  expect(boundaries.overlay.borderTopWidth).toBe('1px');
  expect(boundaries.overlay.boxShadow).not.toBe('none');
}

test.describe('shared Surface migration contract', () => {
  test('keeps the four semantic levels visually distinct in both themes without a glass level', async ({ page }) => {
    await openFixture(page, 1024, 768);

    for (const theme of ['light', 'dark'] as const) {
      await page.evaluate((value) => localStorage.setItem('theme', value), theme);
      await page.reload();
      await expect(page.locator('html')).toHaveClass(new RegExp(`(?:^|\\s)${theme}(?:\\s|$)`));
      for (const level of ['canvas', 'section', 'interactive', 'overlay'] as const) {
        await expect(page.getByTestId(`surface-${level}`)).toHaveAttribute('data-surface-level', level);
      }
      await expect(page.locator('[data-surface-level="glass"]')).toHaveCount(0);
      expectSurfaceBoundaryContract(await surfaceBoundaries(page));
    }
  });

  test('resolves semantic fill, divider, and ring tokens in both themes', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 667 });

    await page.goto('/e2e/surface-contract-fixture.html');
    await page.evaluate(() => localStorage.setItem('theme', 'light'));
    await page.reload();
    await expect(page.locator('html')).toHaveClass(/(?:^|\s)light(?:\s|$)/);
    const light = await themeTokenStyles(page);

    await page.evaluate(() => localStorage.setItem('theme', 'dark'));
    await page.reload();
    await expect(page.locator('html')).toHaveClass(/(?:^|\s)dark(?:\s|$)/);
    const dark = await themeTokenStyles(page);

    for (const styles of [light, dark]) {
      expect(styles.fill).not.toBe('rgba(0, 0, 0, 0)');
      expect(styles.divider).not.toBe('rgba(0, 0, 0, 0)');
      expect(styles.ring).not.toBe('none');
    }
    expect(dark.fill).not.toBe(light.fill);
    expect(dark.divider).not.toBe(light.divider);
    expect(dark.ring).not.toBe(light.ring);
  });

  test('contains the semantic panel across all contract viewports', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const viewport of VIEWPORTS) {
      await openFixture(page, viewport.width, viewport.height);
      await expectNoDocumentOverflow(page, `${viewport.width}x${viewport.height}`);
      const panel = await page.getByTestId('migration-panel').boundingBox();
      expect(panel).not.toBeNull();
      expect(panel!.x).toBeGreaterThanOrEqual(0);
      expect(panel!.x + panel!.width).toBeLessThanOrEqual(viewport.width + 1);
    }
  });
});
