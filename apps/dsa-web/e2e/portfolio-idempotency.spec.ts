// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test } from '@playwright/test';
import { loginAsE2eAdmin } from './auth-fixture';

test.describe('portfolio idempotent mobile mutations', () => {
  test('320px trade form locks while pending and reuses its operation ID on retry', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await loginAsE2eAdmin(page);

    const accountName = `Mobile ${Date.now()}`;
    const accountResponse = await page.request.post('/api/v1/portfolio/accounts', {
      data: {
        name: accountName,
        broker: 'E2E',
        market: 'us',
        base_currency: 'USD',
      },
    });
    expect(accountResponse.ok(), await accountResponse.text()).toBe(true);
    const account = await accountResponse.json() as { id: number };

    await page.goto('/portfolio');
    await expect(page.getByRole('heading', { name: '持仓管理' })).toBeVisible();
    const accountSelect = page.getByRole('combobox', { name: '账户视图' });
    await accountSelect.click();
    await page.locator(`[role="option"][data-value="${account.id}"]`).click();
    await expect(page.getByRole('button', { name: '录入交易' })).toBeEnabled();

    const requests: Array<{ operationId: string; headerId: string | undefined }> = [];
    let releaseFirstRequest!: () => void;
    let markFirstRequestStarted!: () => void;
    const firstRequestGate = new Promise<void>((resolve) => { releaseFirstRequest = resolve; });
    const firstRequestStarted = new Promise<void>((resolve) => { markFirstRequestStarted = resolve; });
    await page.route('**/api/v1/portfolio/trades', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue();
        return;
      }
      const payload = route.request().postDataJSON() as { operation_id: string };
      requests.push({
        operationId: payload.operation_id,
        headerId: route.request().headers()['idempotency-key'],
      });
      if (requests.length === 1) {
        markFirstRequestStarted();
        await firstRequestGate;
        await route.fulfill({
          status: 504,
          contentType: 'application/json',
          body: JSON.stringify({
            error: 'upstream_timeout',
            message: 'simulated timeout after commit',
            params: {},
            details: null,
            trace_id: 'portfolio-e2e-timeout',
          }),
        });
        return;
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 901 }) });
    });

    await page.getByRole('button', { name: '录入交易' }).click();
    const dialog = page.getByRole('dialog', { name: '手工录入：交易' });
    await dialog.getByLabel('股票代码').fill('AAPL');
    await dialog.getByLabel('数量').fill('2');
    await dialog.getByLabel('成交价').fill('210');
    await dialog.getByRole('button', { name: '提交交易' }).click();
    await firstRequestStarted;

    await expect(dialog.getByLabel('股票代码')).toBeDisabled();
    await expect(dialog.getByLabel('数量')).toBeDisabled();
    await expect(dialog.getByRole('button', { name: '提交中' })).toBeDisabled();
    await expect(dialog.getByRole('button', { name: '关闭', exact: true })).toBeDisabled();
    await expect(dialog).toBeVisible();

    const dateBox = await dialog.getByRole('textbox', { name: '交易日期', exact: true }).boundingBox();
    const sideBox = await dialog.getByRole('combobox', { name: '买卖方向' }).boundingBox();
    expect(dateBox).not.toBeNull();
    expect(sideBox).not.toBeNull();
    expect(sideBox!.y).toBeGreaterThanOrEqual(dateBox!.y + dateBox!.height);
    for (const control of [dateBox!, sideBox!]) {
      expect(control.x).toBeGreaterThanOrEqual(0);
      expect(control.x + control.width).toBeLessThanOrEqual(320);
    }

    releaseFirstRequest();
    await expect(dialog.getByText('请求失败', { exact: true })).toBeVisible();
    await expect(dialog.getByLabel('股票代码')).toHaveValue('AAPL');
    await dialog.getByRole('button', { name: '提交交易' }).click();
    await expect(dialog).toBeHidden();

    expect(requests).toHaveLength(2);
    expect(requests[0].operationId).toMatch(/^portfolio-trade-/);
    expect(requests[0].headerId).toBe(requests[0].operationId);
    expect(requests[1]).toEqual(requests[0]);
  });
});
