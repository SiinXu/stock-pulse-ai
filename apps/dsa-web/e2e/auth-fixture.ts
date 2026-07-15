import { expect, type Page } from '@playwright/test';

type AuthStatus = {
  authEnabled: boolean;
  loggedIn: boolean;
  passwordSet?: boolean;
  setupState: 'enabled' | 'password_retained' | 'no_password';
};

const smokePassword = process.env.DSA_WEB_SMOKE_PASSWORD || 'dsa-e2e-smoke';

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

  const submitButton = page.getByRole('button', { name: /授权进入工作台|完成设置并登录/ });
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
