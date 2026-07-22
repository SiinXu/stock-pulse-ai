// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type ConsoleMessage, type Request } from '@playwright/test';
import { buildSettingsHref } from '../src/routing/routes';
import { getE2eAuthStatus, loginAsE2eAdmin } from './auth-fixture';

const firstRunPassword = process.env.DSA_WEB_SMOKE_PASSWORD || 'dsa-e2e-smoke';
const interactionCanary = process.env.DSA_PLAYWRIGHT_ARTIFACT_CANARY
  || 'stockpulse-e2e-credential-interaction-canary';
const baseSettingsHref = buildSettingsHref({ section: 'base', view: 'base' });
const modelConnectionsHref = buildSettingsHref({ section: 'ai_models', view: 'connections' });

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

test('first admin password stays isolated from the first-run Provider API key', async ({ page }, testInfo) => {
  expect(testInfo.project.use.trace, 'credential-bearing acceptance must not create browser traces').toBe('off');
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

  await page.goto(`/login?${new URLSearchParams({ redirect: baseSettingsHref })}`);
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
  await page.waitForURL(`**${baseSettingsHref}`);

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

test('Provider secret reveal, native copy, and clear stay out of diagnostics', async ({ page }, testInfo) => {
  expect(testInfo.project.use.trace, 'credential-bearing acceptance must not create browser traces').toBe('off');
  await loginAsE2eAdmin(page);
  await page.goto(modelConnectionsHref);
  await expect(page.getByRole('heading', { name: '模型接入' })).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: /添加模型服务/ }).first().click();
  const dialog = page.getByRole('dialog', { name: '添加模型服务' });
  await dialog.getByLabel('选择模型服务商').click();
  await dialog.locator('[role="option"][data-value="openai"]').click();
  await dialog.getByRole('button', { name: '下一步' }).click();

  const providerCredential = dialog.getByLabel('API 密钥');
  await expect(providerCredential).toHaveAttribute('name', 'stockpulse-provider-api-key');
  await expect(providerCredential).toHaveAttribute('autocomplete', 'off');
  const credentialSideEffects: string[] = [];
  const browserDiagnostics: string[] = [];
  let credentialReachedRequest = false;
  const recordRequest = (request: Request) => {
    if (isCredentialSideEffect(request)) credentialSideEffects.push(`${request.method()} ${request.url()}`);
    const requestMaterial = `${request.url()}\n${request.postData() ?? ''}`;
    if (requestMaterial.includes(interactionCanary)) credentialReachedRequest = true;
  };
  const recordConsole = (message: ConsoleMessage) => browserDiagnostics.push(message.text());
  const recordPageError = (error: Error) => browserDiagnostics.push(error.message);
  page.on('request', recordRequest);
  page.on('console', recordConsole);
  page.on('pageerror', recordPageError);
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], {
    origin: new URL(page.url()).origin,
  });

  let revealWorked = false;
  let clipboardMatches = false;
  let clearWorked = false;
  let hideWorked = false;
  try {
    await providerCredential.fill(interactionCanary);
    await dialog.getByRole('button', { name: '显示内容' }).click();
    revealWorked = await providerCredential.getAttribute('type') === 'text';
    await providerCredential.selectText();
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+C' : 'Control+C');
    clipboardMatches = await page.evaluate(async (expected) => (
      await navigator.clipboard.readText()
    ) === expected, interactionCanary);
    await page.keyboard.press('Backspace');
    clearWorked = await providerCredential.inputValue() === '';
    await dialog.getByRole('button', { name: '隐藏内容' }).click();
    hideWorked = await providerCredential.getAttribute('type') === 'password';
  } finally {
    await providerCredential.fill('').catch(() => undefined);
    await page.evaluate(() => navigator.clipboard.writeText('')).catch(() => undefined);
    page.off('request', recordRequest);
    page.off('console', recordConsole);
    page.off('pageerror', recordPageError);
  }

  expect(revealWorked, 'Provider secret reveal must expose only the local input value').toBe(true);
  expect(clipboardMatches, 'native copy must preserve the local credential value').toBe(true);
  expect(clearWorked, 'native clear must remove the local credential value').toBe(true);
  expect(hideWorked, 'Provider secret must return to password rendering after the interaction').toBe(true);
  expect(credentialSideEffects).toEqual([]);
  expect(credentialReachedRequest, 'credential interactions must remain browser-local').toBe(false);
  expect(
    browserDiagnostics.some((message) => message.includes(interactionCanary)),
    'credential interactions must not reach browser console or page-error diagnostics',
  ).toBe(false);
  await expect(providerCredential).toHaveValue('');
});
