// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Request } from '@playwright/test';
import { getE2eAuthStatus } from './auth-fixture';

const firstRunPassword = process.env.DSA_WEB_SMOKE_PASSWORD || 'dsa-e2e-smoke';

function isCredentialSideEffect(request: Request): boolean {
  const { pathname } = new URL(request.url());
  return (
    request.method() === 'POST'
    && pathname === '/api/v1/system/config/llm/test-channel'
  ) || (
    request.method() === 'PUT'
    && pathname === '/api/v1/system/config'
  );
}

test('first admin password stays isolated from the first-run Provider API key', async ({ page }) => {
  const status = await getE2eAuthStatus(page);
  expect(status.passwordSet, 'credential-boundary scenario requires the fresh E2E auth store').toBe(false);

  await page.route('**/api/v1/system/config/setup/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        is_complete: false,
        ready_for_smoke: false,
        required_missing_keys: ['LLM_CHANNELS'],
        next_step_key: 'LLM_CHANNELS',
        checks: [],
      }),
    });
  });

  await page.goto('/login?redirect=%2Fsettings%3Fsection%3Dbase%26view%3Dbase');
  const adminPassword = page.getByLabel('管理员密码');
  const confirmation = page.getByLabel('确认密码');
  await expect(adminPassword).toHaveAttribute('name', 'stockpulse-admin-new-password');
  await expect(adminPassword).toHaveAttribute('autocomplete', 'new-password');
  await expect(confirmation).toHaveAttribute('name', 'stockpulse-admin-new-password-confirmation');
  await expect(confirmation).toHaveAttribute('autocomplete', 'new-password');
  await adminPassword.fill(firstRunPassword);
  await confirmation.fill(firstRunPassword);

  await Promise.all([
    page.waitForResponse((response) => (
      response.url().includes('/api/v1/auth/login') && response.status() === 200
    )),
    page.getByRole('button', { name: '完成设置并登录' }).click(),
  ]);
  await page.waitForURL(/\/settings\?section=base&view=base$/);

  await page.getByRole('button', { name: '启动向导' }).click();
  const dialog = page.getByRole('dialog', { name: '快速配置向导' });
  await dialog.getByRole('button', { name: /云 API/ }).click();

  const credentialSideEffects: string[] = [];
  const recordSideEffect = (request: Request) => {
    if (isCredentialSideEffect(request)) credentialSideEffects.push(`${request.method()} ${request.url()}`);
  };
  page.on('request', recordSideEffect);
  await dialog.getByRole('button', { name: '下一步' }).click();

  const providerCredential = dialog.getByRole('textbox', { name: 'API 密钥', exact: true });
  await expect(providerCredential).toHaveAttribute('name', 'stockpulse-provider-api-key');
  await expect(providerCredential).toHaveAttribute('autocomplete', 'off');
  await expect(providerCredential).toHaveValue('');
  await page.evaluate(() => new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  }));
  expect(credentialSideEffects).toEqual([]);
  await expect(providerCredential).toHaveValue('');
  page.off('request', recordSideEffect);
});
