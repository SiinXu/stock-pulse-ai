// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, type Page } from '@playwright/test';

type AuthStatus = {
  authEnabled: boolean;
  loggedIn: boolean;
  passwordSet?: boolean;
  setupState: 'enabled' | 'password_retained' | 'no_password';
};

const smokePassword = process.env.DSA_WEB_SMOKE_PASSWORD || 'dsa-e2e-smoke';
const smokeBackendPort = Number(process.env.DSA_WEB_SMOKE_BACKEND_PORT || 18100);
const smokeBackendOrigin = `http://127.0.0.1:${smokeBackendPort}`;

type ConfigUpdateItem = { key: string; value: string };

export async function updateE2eConfigOutsidePlaywrightTrace(items: ConfigUpdateItem[]): Promise<void> {
  // Playwright traces retain API request bodies. Keep generated credentials in
  // this native-fetch setup boundary, then exercise all masked UI/API flows normally.
  const login = await fetch(`${smokeBackendOrigin}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ password: smokePassword, passwordConfirm: smokePassword }),
  });
  if (!login.ok) throw new Error(`E2E native login failed (${login.status})`);
  const cookie = login.headers.get('set-cookie')?.split(';', 1)[0];
  if (!cookie) throw new Error('E2E native login did not return a session cookie');

  const configResponse = await fetch(`${smokeBackendOrigin}/api/v1/system/config`, {
    headers: { cookie },
  });
  if (!configResponse.ok) throw new Error(`E2E native config read failed (${configResponse.status})`);
  const config = await configResponse.json() as { config_version: string; mask_token: string };

  const update = await fetch(`${smokeBackendOrigin}/api/v1/system/config`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json', cookie },
    body: JSON.stringify({
      config_version: config.config_version,
      mask_token: config.mask_token,
      reload_now: true,
      items,
    }),
  });
  if (!update.ok) throw new Error(`E2E native config update failed (${update.status})`);
}

// HomePage picks `experienceMode = 'beginner'` when
// GET /api/v1/system/config/setup/status returns `is_complete: false`
// (see apps/dsa-web/src/pages/HomePage.tsx around the experienceMode
// derivation). In beginner mode the primary CTA becomes `home.quickAnalyze`
// and the report region renders `BeginnerReportSummary` instead of the full
// report, so specs that assert professional-mode surface (`分析`,
// `完整分析报告`, full report body) must force setup-status to complete before
// navigating.
//
// Call this before `loginAsE2eAdmin` (or any navigation that lands on `/`) in
// tests that need the professional experience. Kept opt-in — do not fold into
// `loginAsE2eAdmin`, so beginner-mode surface remains covered by tests that
// deliberately skip this helper.
export async function mockCompletedSetupStatus(page: Page): Promise<void> {
  await page.route('**/api/v1/system/config/setup/status', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        is_complete: true,
        ready_for_smoke: true,
        required_missing_keys: [],
        next_step_key: null,
        checks: [],
      }),
    });
  });
}

export async function getE2eAuthStatus(page: Page): Promise<AuthStatus> {
  const response = await page.request.get('/api/v1/auth/status');
  expect(response.ok(), `auth status failed (${response.status()})`).toBe(true);
  const status = await response.json() as AuthStatus;
  expect(status.authEnabled, 'Playwright backend must run with authentication enabled').toBe(true);
  return status;
}

export async function loginAsE2eAdmin(page: Page): Promise<void> {
  const status = await getE2eAuthStatus(page);
  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded');
  await expect(page).toHaveURL(/\/login(?:\?|$)/);

  const passwordInput = page.locator('#password');
  await expect(passwordInput).toBeVisible({ timeout: 10_000 });
  await passwordInput.fill(smokePassword);

  const confirmation = page.locator('#passwordConfirm');
  if (!status.passwordSet) {
    await expect(confirmation).toBeVisible();
    await confirmation.fill(smokePassword);
  } else if (await confirmation.isVisible().catch(() => false)) {
    await confirmation.fill(smokePassword);
  }

  const submitButton = page.getByRole('button', {
    name: /授权进入工作台|完成设置并登录|Enter workspace|Finish setup and sign in/,
  });
  await expect(submitButton).toBeVisible();
  await Promise.all([
    page.waitForResponse(
      (response) => response.url().includes('/api/v1/auth/login') && response.status() === 200,
      { timeout: 20_000 },
    ),
    submitButton.click(),
  ]);
  await page.waitForURL('/', { timeout: 20_000 });
  await page.waitForLoadState('domcontentloaded');
}
