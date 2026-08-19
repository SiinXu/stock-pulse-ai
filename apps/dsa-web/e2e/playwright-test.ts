// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { test as base } from '@playwright/test';
import { disposePlaywrightRoutes } from './playwrightRouteTeardown';

export {
  chromium,
  expect,
} from '@playwright/test';
export type {
  Browser,
  ConsoleMessage,
  Locator,
  Page,
  Request,
  Route,
} from '@playwright/test';

/**
 * Shared Playwright `test` for this package. An auto fixture unroutes page and
 * context handlers after each test body and before Playwright closes the page,
 * so in-flight `route.fetch()` callbacks cannot outlive teardown.
 */
export const test = base.extend<{ disposeRegisteredRoutes: void }>({
  disposeRegisteredRoutes: [async ({ page, context }, use) => {
    await use();
    await disposePlaywrightRoutes(page, context);
  }, { auto: true }],
});
