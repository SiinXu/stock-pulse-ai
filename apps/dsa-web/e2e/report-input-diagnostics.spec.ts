// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Page } from '@playwright/test';

const VIEWPORTS = [
  { width: 1280, height: 900 },
  { width: 390, height: 844 },
  { width: 320, height: 700 },
] as const;

async function openExpandedFixture(page: Page, width: number, height: number) {
  await page.setViewportSize({ width, height });
  await page.goto('/e2e/analysis-context-summary-fixture.html');
  const summary = page.getByTestId('analysis-context-summary');
  await expect(summary).not.toHaveAttribute('open', '');
  await summary.locator('summary').click();
  await expect(summary).toHaveAttribute('open', '');
  return summary;
}

async function expectNoHorizontalOverflow(page: Page, label: string) {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content, `${label}: ${dimensions.content}px content in ${dimensions.viewport}px viewport`)
    .toBeLessThanOrEqual(dimensions.viewport + 1);
}

test.describe('report input diagnostics', () => {
  for (const viewport of VIEWPORTS) {
    test(`keeps diagnostic content reachable at ${viewport.width}px`, async ({ page }) => {
      const summary = await openExpandedFixture(page, viewport.width, viewport.height);

      await expect(summary.getByText(/News was not included in this LLM run/)).toBeVisible();
      await expect(summary.getByText(/related news on the report page is loaded separately/)).toBeVisible();
      await expect(summary.getByText(/Diagnostic code: news_context_missing/)).toBeVisible();
      await expect(summary.getByText('Source: Input source not recorded')).toHaveCount(3);
      await expect(summary.getByText(/Only part of the data was included/)).toBeVisible();
      await expect(summary.getByText(/This analysis used estimated data/)).toBeVisible();
      await expect(summary.getByText(/not supported for the current market or symbol/)).toBeVisible();
      await expect(summary.locator('.home-subpanel')).toHaveCount(0);

      const blockOverflow = await summary.locator('[data-testid^="analysis-context-block-"]').evaluateAll((blocks) => (
        blocks.map((block) => ({
          width: block.clientWidth,
          content: block.scrollWidth,
        }))
      ));
      for (const [index, dimensions] of blockOverflow.entries()) {
        expect(dimensions.content, `block ${index} content width`).toBeLessThanOrEqual(dimensions.width + 1);
      }
      await expectNoHorizontalOverflow(page, `${viewport.width}px diagnostics`);
    });
  }

  test('uses one column on mobile and two columns on desktop', async ({ page }) => {
    let summary = await openExpandedFixture(page, 390, 844);
    const mobileQuote = await summary.getByTestId('analysis-context-block-quote').boundingBox();
    const mobileNews = await summary.getByTestId('analysis-context-block-news').boundingBox();
    expect(mobileQuote).not.toBeNull();
    expect(mobileNews).not.toBeNull();
    expect(mobileNews!.x).toBeCloseTo(mobileQuote!.x, 0);
    expect(mobileNews!.y).toBeGreaterThanOrEqual(mobileQuote!.y + mobileQuote!.height - 1);

    summary = await openExpandedFixture(page, 1280, 900);
    const desktopQuote = await summary.getByTestId('analysis-context-block-quote').boundingBox();
    const desktopNews = await summary.getByTestId('analysis-context-block-news').boundingBox();
    expect(desktopQuote).not.toBeNull();
    expect(desktopNews).not.toBeNull();
    expect(desktopNews!.y).toBeCloseTo(desktopQuote!.y, 0);
    expect(desktopNews!.x).toBeGreaterThan(desktopQuote!.x + desktopQuote!.width - 1);
  });
});
