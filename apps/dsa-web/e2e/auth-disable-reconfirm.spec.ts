// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Page } from '@playwright/test';
import { buildSettingsHref } from '../src/routing/routes';
import { loginAsE2eAdmin } from './auth-fixture';

test.use({ locale: 'zh-CN' });
test.describe.configure({ timeout: 90_000 });

const UI_LANGUAGE_STORAGE_KEY = 'dsa.uiLanguage';
const smokePassword = process.env.DSA_WEB_SMOKE_PASSWORD || 'dsa-e2e-smoke';
const securitySettingsHref = buildSettingsHref({
  section: 'system_security',
  view: 'security',
});

async function loginAndOpenAuthSettings(page: Page) {
  await page.addInitScript((storageKey) => {
    window.localStorage.setItem(storageKey, 'zh');
  }, UI_LANGUAGE_STORAGE_KEY);
  await loginAsE2eAdmin(page);
  await page.goto(securitySettingsHref);
  // Settings is a lazy route + config bootstrap; wait for the auth card heading.
  await expect(page.getByRole('heading', { name: '认证与登录保护' })).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByText('已启用', { exact: true }).first()).toBeVisible();
}

async function beginDisableAuth(page: Page) {
  // Auth status checkbox label switches between 已启用 / 未启用 with desiredEnabled.
  const enableCheckbox = page.getByRole('checkbox', { name: /已启用|未启用/ }).first();
  await expect(enableCheckbox).toBeChecked();
  await enableCheckbox.click();
  await expect(enableCheckbox).not.toBeChecked();
  await expect(page.getByLabel('当前管理员密码')).toBeVisible();
  await expect(page.getByRole('button', { name: '关闭认证' })).toBeVisible();
}

test.describe('Auth disable re-confirmation', () => {
  test('blocks disable without the current password (client gate)', async ({ page }) => {
    let settingsPosts = 0;
    page.on('request', (request) => {
      if (
        request.method() === 'POST'
        && new URL(request.url()).pathname === '/api/v1/auth/settings'
      ) {
        settingsPosts += 1;
      }
    });

    await loginAndOpenAuthSettings(page);
    await beginDisableAuth(page);

    await page.getByRole('button', { name: '关闭认证' }).click();

    await expect(page.getByText('认证设置失败')).toBeVisible();
    // Hint + alert both use the same copy; scope to the failure title's alert body.
    await expect(
      page.locator('.break-words').filter({ hasText: '关闭认证前请输入当前管理员密码' }),
    ).toBeVisible();
    expect(settingsPosts).toBe(0);
    // Auth remains enabled — no session/auth-mode mutation.
    await expect(page.getByText('已启用', { exact: true }).first()).toBeVisible();
  });

  test('server rejects disable when the current password is wrong', async ({ page }) => {
    await loginAndOpenAuthSettings(page);
    await beginDisableAuth(page);

    await page.getByLabel('当前管理员密码').fill(`wrong-${smokePassword}`);

    const settingsResponsePromise = page.waitForResponse((response) => (
      response.url().includes('/api/v1/auth/settings')
      && response.request().method() === 'POST'
    ));
    await page.getByRole('button', { name: '关闭认证' }).click();
    const response = await settingsResponsePromise;

    expect(response.status()).toBe(401);
    // Reading the body can race with the shared 401 → /login navigation; status is enough
    // to prove the server enforced current-password verification (missing password is 400).

    // The shared axios interceptor treats any 401 as session loss and forces login.
    // Server still keeps authentication enabled after a rejected re-confirmation.
    await page.waitForURL(/\/login(?:\?|$)/, { timeout: 15_000 });
    const status = await page.request.get('/api/v1/auth/status');
    expect(status.ok()).toBe(true);
    const body = await status.json() as { authEnabled: boolean };
    expect(body.authEnabled).toBe(true);
  });
});
