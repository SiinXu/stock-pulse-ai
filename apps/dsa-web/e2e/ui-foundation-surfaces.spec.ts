// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Page, type Route } from '@playwright/test';
import { loginAsE2eAdmin } from './auth-fixture';

const usageDashboard = {
  period: 'month',
  from_date: '2026-06-01',
  to_date: '2026-06-11',
  total_calls: 3,
  total_prompt_tokens: 120,
  total_completion_tokens: 280,
  total_tokens: 400,
  by_call_type: [
    {
      call_type: 'analysis',
      calls: 3,
      prompt_tokens: 100,
      completion_tokens: 200,
      total_tokens: 300,
    },
  ],
  by_model: [
    {
      model: 'fixture/model',
      calls: 3,
      prompt_tokens: 100,
      completion_tokens: 200,
      total_tokens: 300,
      max_total_tokens: 180,
    },
  ],
  recent_calls: [
    {
      id: 1,
      called_at: '2026-06-11T09:30:00',
      call_type: 'analysis',
      model: 'fixture/model',
      stock_code: '600519',
      prompt_tokens: 40,
      completion_tokens: 80,
      total_tokens: 120,
    },
  ],
};

const emptyUsageDashboard = {
  ...usageDashboard,
  total_calls: 0,
  total_prompt_tokens: 0,
  total_completion_tokens: 0,
  total_tokens: 0,
  by_call_type: [],
  by_model: [],
  recent_calls: [],
};

const viewports = [
  { width: 1440, height: 900 },
  { width: 1280, height: 820 },
  { width: 1024, height: 768 },
  { width: 900, height: 800 },
  { width: 768, height: 900 },
  { width: 767, height: 900 },
  { width: 390, height: 844 },
  { width: 390, height: 667 },
  { width: 320, height: 700 },
] as const;

async function fulfillJson(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function expectNoDocumentOverflow(page: Page, label: string): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content, `${label}: ${dimensions.content}px content in ${dimensions.viewport}px viewport`)
    .toBeLessThanOrEqual(dimensions.viewport + 1);
}

test.describe('surface and task-state foundation', () => {
  test('uses one stable state surface while loading and when usage is empty', async ({ page }) => {
    await loginAsE2eAdmin(page);
    let releaseResponse!: () => void;
    const responseGate = new Promise<void>((resolve) => {
      releaseResponse = resolve;
    });
    await page.route('**/api/v1/usage/dashboard**', async (route) => {
      await responseGate;
      await fulfillJson(route, emptyUsageDashboard);
    });

    await page.goto('/usage');
    const loading = page.locator('[data-state-panel="loading"]');
    await expect(loading).toHaveCount(1);
    await expect(loading).toHaveAttribute('role', 'status');
    await expect(loading).toHaveAttribute('aria-busy', 'true');
    await expect(page.locator('[data-state-panel]')).toHaveCount(1);
    await expect(page.getByText('总 Token')).toHaveCount(0);
    await expect(page.getByRole('table')).toHaveCount(0);

    releaseResponse();
    const empty = page.locator('[data-state-panel="empty"]');
    await expect(empty).toHaveCount(1);
    await expect(empty).not.toHaveAttribute('role', 'status');
    await expect(page.locator('[data-state-panel]')).toHaveCount(1);
    await expect(page.getByText('总 Token')).toHaveCount(0);
    await expect(page.getByRole('table')).toHaveCount(0);

    const emptyBoundary = await empty.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        borderTopWidth: style.borderTopWidth,
        boxShadow: style.boxShadow,
      };
    });
    expect(emptyBoundary).toEqual({ borderTopWidth: '0px', boxShadow: 'none' });
  });

  test('recovers from an initial error and preserves successful data after refresh failure', async ({ page }) => {
    await loginAsE2eAdmin(page);
    let responseMode: 'error' | 'success' | 'refresh-error' = 'error';
    const requestCounts = { error: 0, success: 0, 'refresh-error': 0 };
    await page.route('**/api/v1/usage/dashboard**', async (route) => {
      requestCounts[responseMode] += 1;
      if (responseMode === 'success') {
        await fulfillJson(route, usageDashboard);
        return;
      }
      await fulfillJson(route, {
        error: 'usage_unavailable',
        message: 'Usage data is temporarily unavailable.',
        params: {},
      }, 503);
    });

    await page.goto('/usage');
    const initialError = page.locator('[data-state-panel="error"]');
    await expect(initialError).toHaveCount(1);
    await expect(initialError).toHaveAttribute('role', 'alert');
    responseMode = 'success';
    await page.getByRole('button', { name: '重试' }).click();

    await expect(page.getByText('400', { exact: true })).toBeVisible();
    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.locator('[data-state-panel]')).toHaveCount(0);

    responseMode = 'refresh-error';
    await page.getByRole('button', { name: '刷新' }).click();
    await expect(page.locator('[data-alert-tone="danger"]')).toHaveCount(1);
    await expect(page.getByText('400', { exact: true })).toBeVisible();
    await expect(page.getByRole('table')).toBeVisible();
    expect(requestCounts.error).toBeGreaterThan(0);
    expect(requestCounts.success).toBeGreaterThan(0);
    expect(requestCounts['refresh-error']).toBeGreaterThan(0);
  });

  test('does not present a stale snapshot under a newly selected period', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await page.route('**/api/v1/usage/dashboard**', async (route) => {
      const period = new URL(route.request().url()).searchParams.get('period');
      if (period === 'today') {
        await fulfillJson(route, {
          error: 'usage_unavailable',
          message: 'Today usage is temporarily unavailable.',
          params: {},
        }, 503);
        return;
      }
      await fulfillJson(route, usageDashboard);
    });

    await page.goto('/usage');
    await expect(page.getByText('400', { exact: true })).toBeVisible();
    await expect(page.getByRole('table')).toBeVisible();
    await page.getByRole('tab', { name: '今日' }).click();

    await expect(page.locator('[data-state-panel="error"]')).toHaveCount(1);
    await expect(page.getByText('400', { exact: true })).toHaveCount(0);
    await expect(page.getByRole('table')).toHaveCount(0);
  });

  test('keeps semantic surface boundaries responsive in both themes', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await page.route('**/api/v1/usage/dashboard**', async (route) => {
      await fulfillJson(route, usageDashboard);
    });
    await page.goto('/usage');
    await expect(page.getByText('400', { exact: true })).toBeVisible();

    const modelSection = page.getByRole('region', { name: '模型用量' });
    const callTypeSection = page.getByRole('region', { name: '调用类型' });
    await expect(modelSection).toHaveAttribute('data-surface-level', 'canvas');
    await expect(callTypeSection).toHaveAttribute('data-surface-level', 'section');

    const sectionBoundary = await callTypeSection.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        borderTopWidth: style.borderTopWidth,
        boxShadow: style.boxShadow,
        backgroundColor: style.backgroundColor,
      };
    });
    expect(sectionBoundary.borderTopWidth).toBe('0px');
    expect(sectionBoundary.boxShadow).toBe('none');
    expect(sectionBoundary.backgroundColor).not.toBe('rgba(0, 0, 0, 0)');

    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await expect(page.getByRole('heading', { level: 1, name: 'Token 用量监控' })).toBeVisible();
      await expectNoDocumentOverflow(page, `${viewport.width}x${viewport.height}`);
    }

    await page.evaluate(() => localStorage.setItem('theme', 'dark'));
    await page.reload();
    await expect(page.locator('html')).toHaveClass(/(?:^|\s)dark(?:\s|$)/);
    await expect(page.getByText('400', { exact: true })).toBeVisible();
    await expectNoDocumentOverflow(page, 'dark 320x700');
  });
});
