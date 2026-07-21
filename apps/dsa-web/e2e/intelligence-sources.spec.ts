// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test } from '@playwright/test';
import { loginAsE2eAdmin } from './auth-fixture';

// Smoke coverage for the Intel Sources tab only. The
// `/api/v1/intelligence/*` endpoints are mocked so the panel renders
// deterministically without depending on live feeds or seeded data.
test.describe('intelligence sources settings', () => {
  test('renders mocked intelligence sources on the Intel Sources tab', async ({ page }) => {
    await page.route(/\/api\/v1\/intelligence\/sources\/templates/, async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            { template_id: 'cn-market-rss', name: 'A-share market RSS', source_type: 'rss', url: 'https://template.example/rss', scope_type: 'market', market: 'cn' },
          ],
          total: 1,
        }),
      });
    });
    await page.route(/\/api\/v1\/intelligence\/sources(\?|$)/, async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 1,
              name: 'E2E Intelligence Feed',
              source_type: 'rss',
              url: 'https://feed.example/rss',
              enabled: true,
              scope_type: 'market',
              market: 'cn',
              last_status: 'ok',
              last_fetched_at: '2026-07-19T00:00:00Z',
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        }),
      });
    });

    await loginAsE2eAdmin(page);
    await page.goto('/settings?section=data_sources&view=intelligence');

    await expect(page.getByText('E2E Intelligence Feed')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('A-share market RSS')).toBeVisible();
  });
});
