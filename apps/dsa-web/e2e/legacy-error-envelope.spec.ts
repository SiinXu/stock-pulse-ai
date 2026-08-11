// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test } from '@playwright/test';
import { LEGACY_ROUTE_PATHS } from '../src/routing/routes';
import { loginAsE2eAdmin } from './auth-fixture';

const uiLanguageStorageKey = 'dsa.uiLanguage';

test.describe('legacy error envelope compatibility', () => {
  test('localizes a legacy-only detail without exposing operator diagnostics', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await page.evaluate((key) => localStorage.setItem(key, 'en'), uiLanguageStorageKey);

    const legacyEnvelope = {
      error: 'conflict',
      message: 'Legacy alert-rules diagnostic for operators only',
      params: {},
      detail: {
        source: 'legacy-alert-rules',
        request_id: 'legacy-detail-browser-acceptance',
      },
      trace_id: 'trace-legacy-detail-e2e',
    };
    expect('details' in legacyEnvelope).toBe(false);

    await page.route('**/api/v1/alerts/rules**', async (route) => {
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify(legacyEnvelope),
      });
    });

    await page.goto(LEGACY_ROUTE_PATHS.alerts);
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');

    const alert = page.getByRole('alert').filter({ hasText: 'Operation conflict' });
    await expect(alert).toBeVisible();
    await expect(alert.getByText('Operation conflict', { exact: true })).toBeVisible();
    await expect(alert.getByText('The data changed. Refresh and try again.', { exact: true })).toBeVisible();

    await expect(alert.getByText('View details', { exact: true })).toHaveCount(0);
    await expect(alert.locator('pre')).toHaveCount(0);
    await expect(alert).not.toContainText('Legacy alert-rules diagnostic for operators only');
    await expect(alert).not.toContainText('legacy-alert-rules');
    await expect(alert).not.toContainText('legacy-detail-browser-acceptance');
    await expect(alert).not.toContainText('trace-legacy-detail-e2e');
  });
});
