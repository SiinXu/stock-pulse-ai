// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test } from '@playwright/test';
import { APP_ROUTE_PATHS } from '../src/routing/routes';
import { loginAsE2eAdmin, mockCompletedSetupStatus } from './auth-fixture';

test.describe('Shell global actions', () => {
  test.use({ locale: 'zh-CN' });

  test('keeps one Bell and coordinates Search, the command palette, and mobile navigation', async ({ page }) => {
    await mockCompletedSetupStatus(page);
    await loginAsE2eAdmin(page);

    await expect(page.getByRole('button', { name: /^通知/ })).toHaveCount(1);
    await page.getByRole('button', { name: '搜索' }).click();

    let palette = page.getByRole('dialog', { name: '快速前往' });
    await expect(palette).toBeVisible();
    await expect(palette.getByText('⌘K')).toHaveCount(0);
    await palette.getByRole('button', { name: '开始分析' }).click();
    await expect(page).toHaveURL(new RegExp(`${APP_ROUTE_PATHS.researchAnalysis}$`));

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole('button', { name: /^通知/ })).toHaveCount(1);
    await page.getByRole('button', { name: '打开导航菜单' }).click();

    const drawer = page.getByRole('dialog', { name: '导航菜单' });
    await expect(drawer).toBeVisible();
    await drawer.getByRole('button', { name: '搜索' }).click();

    await expect(drawer).toBeHidden();
    palette = page.getByRole('dialog', { name: '快速前往' });
    await expect(palette).toBeVisible();
    await expect(page.locator('button[aria-label^="通知"]')).toHaveCount(1);
  });
});
