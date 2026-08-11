// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Page } from '@playwright/test';

async function openPaginationFixture(page: Page, width: number, density: 'full' | 'compact' | 'auto' = 'full') {
  // Viewport wider than the host so container width is controlled by the fixture, not the chrome.
  await page.setViewportSize({ width: Math.max(width + 120, 900), height: 700 });
  await page.goto(`/e2e/pagination-fixture.html?width=${width}&density=${density}`);
  await expect(page.getByRole('heading', { level: 1, name: 'Pagination reachability' })).toBeVisible();
  await expect(page.getByTestId('pagination-host')).toHaveAttribute('data-container-width', String(width));
  await expect(page.getByRole('navigation')).toBeVisible();
}

type ReachabilityMetrics = {
  computedJustify: string;
  clientWidth: number;
  scrollWidth: number;
  contentWidth: number;
  prevLeftRelativeToNav: number;
  prevFullyVisibleAtMinScroll: boolean;
  firstControlOffset: number;
};

async function measureReachability(page: Page): Promise<ReachabilityMetrics> {
  return page.evaluate(() => {
    const nav = document.querySelector('nav');
    if (!nav) {
      throw new Error('pagination nav not found');
    }
    const prev = nav.querySelector('button');
    if (!prev) {
      throw new Error('prev control not found');
    }

    nav.scrollLeft = 0;
    const navRect = nav.getBoundingClientRect();
    const prevRect = prev.getBoundingClientRect();
    const children = Array.from(nav.children);
    const contentWidth = Math.round(
      children.reduce((sum, el) => sum + el.getBoundingClientRect().width, 0)
      + 8 * Math.max(children.length - 1, 0),
    );

    return {
      computedJustify: getComputedStyle(nav).justifyContent,
      clientWidth: nav.clientWidth,
      scrollWidth: nav.scrollWidth,
      contentWidth,
      prevLeftRelativeToNav: Math.round(prevRect.left - navRect.left),
      prevFullyVisibleAtMinScroll: prevRect.left >= navRect.left - 0.5,
      firstControlOffset: prevRect.left - navRect.left,
    };
  });
}

test.describe('Pagination overflow reachability', () => {
  test('keeps the leading control reachable when full density overflows at 520px', async ({ page }) => {
    await openPaginationFixture(page, 520, 'full');
    const metrics = await measureReachability(page);

    expect(metrics.prevFullyVisibleAtMinScroll, JSON.stringify(metrics)).toBe(true);
    expect(metrics.prevLeftRelativeToNav, JSON.stringify(metrics)).toBeGreaterThanOrEqual(0);
    // Full content width must be scrollable — no start-edge loss from unsafe centering.
    expect(
      Math.abs(metrics.scrollWidth - metrics.contentWidth),
      `scrollWidth ${metrics.scrollWidth} vs contentWidth ${metrics.contentWidth}`,
    ).toBeLessThanOrEqual(1);
  });

  test('preserves desktop centering when the full control set fits at 900px', async ({ page }) => {
    await openPaginationFixture(page, 900, 'full');
    const metrics = await measureReachability(page);

    expect(metrics.scrollWidth, JSON.stringify(metrics)).toBe(metrics.clientWidth);
    expect(metrics.firstControlOffset, JSON.stringify(metrics)).toBeGreaterThan(0);
    expect(metrics.prevFullyVisibleAtMinScroll, JSON.stringify(metrics)).toBe(true);
  });
});
