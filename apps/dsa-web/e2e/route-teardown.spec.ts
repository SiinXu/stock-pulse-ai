// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test } from './playwright-test';

/**
 * Regression for the Playwright lifecycle race where an async `route.fetch()`
 * handler outlives the test body. The shared `test` fixture must unroute with
 * `behavior: 'ignoreErrors'` before Playwright closes the page.
 */
test('unroutes in-flight route.fetch handlers before page teardown', async ({ page }) => {
  let fetchStarted = false;
  await page.route('**/api/v1/auth/status', async (route) => {
    fetchStarted = true;
    const response = await route.fetch();
    await route.fulfill({ response });
  });

  await page.goto('/login');
  await expect.poll(() => fetchStarted).toBe(true);
  await expect(page.locator('#password')).toBeVisible();
});
