// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test } from '@playwright/test';
import { loginAsE2eAdmin } from './auth-fixture';

test('a fresh user without an API key can reach the offline demo report', async ({ page }) => {
  const readinessResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/onboarding/first-run')
    && response.request().method() === 'GET'
    && response.status() === 200
  ));

  await loginAsE2eAdmin(page);

  const readiness = await (await readinessResponse).json() as {
    has_primary_model: boolean;
    config_mutated: boolean;
    demo_available: boolean;
  };
  expect(readiness).toMatchObject({
    has_primary_model: false,
    config_mutated: false,
    demo_available: true,
  });

  const firstRun = page.getByTestId('home-first-run-entry');
  await expect(firstRun).toBeVisible();
  await expect(firstRun.getByTestId('zero-config-first-run-panel')).toBeVisible();

  const demoResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/onboarding/demo-analysis')
    && response.request().method() === 'GET'
    && response.status() === 200
  ));
  await firstRun.getByRole('button', { name: '查看示例分析' }).click();

  const demo = await (await demoResponse).json() as { is_sample: boolean };
  expect(demo.is_sample).toBe(true);
  await expect(firstRun.getByTestId('zero-config-demo-analysis')).toBeVisible();
  await expect(firstRun.getByTestId('beginner-report-summary')).toContainText('600519');
});
