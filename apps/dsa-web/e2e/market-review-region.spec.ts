// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Page, type Route } from '@playwright/test';
import { APP_ROUTE_PATHS } from '../src/routing/routes';
import { loginAsE2eAdmin, mockCompletedSetupStatus } from './auth-fixture';

test.use({ locale: 'zh-CN' });
test.describe.configure({ timeout: 60_000 });

const UI_LANGUAGE_STORAGE_KEY = 'dsa.uiLanguage';
const TASK_ID = 'e2e-market-review-hk-us';
const PERSISTED_REVIEW_ID = 9101;
const REGION_PAYLOAD_MARKER = 'E2E_PER_MARKET_REVIEW_HK_US';

type JsonObject = Record<string, unknown>;

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function login(page: Page) {
  await page.addInitScript((storageKey) => {
    window.localStorage.setItem(storageKey, 'zh');
  }, UI_LANGUAGE_STORAGE_KEY);
  await mockCompletedSetupStatus(page);
  await loginAsE2eAdmin(page);
  await expect(page.getByTestId('home-core-blocks')).toBeVisible({ timeout: 15_000 });
}

function marketReviewHistoryItem(completed: boolean) {
  if (!completed) {
    return {
      total: 0,
      page: 1,
      limit: 10,
      items: [] as JsonObject[],
    };
  }
  return {
    total: 1,
    page: 1,
    limit: 10,
    items: [{
      id: PERSISTED_REVIEW_ID,
      query_id: TASK_ID,
      stock_code: 'MARKET',
      stock_name: '大盘复盘',
      report_type: 'market_review',
      report_language: 'zh',
      created_at: '2026-08-05T12:00:00Z',
      analysis_summary: REGION_PAYLOAD_MARKER,
    }],
  };
}

function marketReviewDetail() {
  return {
    meta: {
      id: PERSISTED_REVIEW_ID,
      query_id: TASK_ID,
      stock_code: 'MARKET',
      stock_name: '大盘复盘',
      report_type: 'market_review',
      report_language: 'zh',
      created_at: '2026-08-05T12:00:00Z',
      model_used: 'e2e/fake-report-model',
    },
    summary: {
      analysis_summary: REGION_PAYLOAD_MARKER,
      operation_advice: '观察量能',
      trend_prediction: '震荡',
      sentiment_score: 61,
    },
    details: {
      context_snapshot: {
        market_review_payload: {
          kind: 'market_review',
          region: 'hk,us',
          title: 'Per-market review fixture',
          sections: [{
            key: 'generation',
            title: 'Generation',
            markdown: REGION_PAYLOAD_MARKER,
          }],
        },
      },
    },
  };
}

test.describe('Per-market market review', () => {
  test('region selection posts scoped regions, then opens the persisted report', async ({ page }) => {
    let reviewCompleted = false;
    let capturedRegion: string | undefined;
    let capturedNotification: boolean | undefined;
    let submissions = 0;

    // Log in first so auth/session bootstrap is not entangled with API fixtures.
    await login(page);

    await page.route('**/api/v1/history**', async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/v1/history' && url.searchParams.get('report_type') === 'market_review') {
        await fulfillJson(route, marketReviewHistoryItem(reviewCompleted));
        return;
      }
      if (url.pathname === `/api/v1/history/${PERSISTED_REVIEW_ID}`) {
        await fulfillJson(route, marketReviewDetail());
        return;
      }
      if (url.pathname === `/api/v1/history/${PERSISTED_REVIEW_ID}/markdown`) {
        await fulfillJson(route, { content: `# ${REGION_PAYLOAD_MARKER}` });
        return;
      }
      if (url.pathname === `/api/v1/history/${PERSISTED_REVIEW_ID}/news`) {
        await fulfillJson(route, { total: 0, items: [] });
        return;
      }
      await route.fallback();
    });

    await page.route('**/api/v1/analysis/market-review', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.fallback();
        return;
      }
      submissions += 1;
      const body = route.request().postDataJSON() as {
        region?: string;
        send_notification?: boolean;
      };
      capturedRegion = body.region;
      capturedNotification = body.send_notification;
      await fulfillJson(route, {
        status: 'accepted',
        message: '大盘复盘任务已提交',
        task_id: TASK_ID,
        region: body.region ?? 'cn',
        send_notification: body.send_notification ?? true,
      }, 202);
    });

    await page.route(`**/api/v1/analysis/status/${TASK_ID}`, async (route) => {
      reviewCompleted = true;
      await fulfillJson(route, {
        task_id: TASK_ID,
        status: 'completed',
        progress: 100,
        region: 'hk,us',
        market_review_report: 'RAW_STATUS_MUST_NOT_RENDER',
      });
    });

    await page.goto(APP_ROUTE_PATHS.researchMarket);
    const regionTrigger = page.getByRole('button', { name: '选择大盘复盘市场' });
    await expect(regionTrigger).toBeVisible({ timeout: 20_000 });

    await regionTrigger.click();
    const regionMenu = page.getByRole('dialog', { name: '选择大盘复盘市场' });
    await expect(regionMenu).toBeVisible();
    await regionMenu.getByRole('checkbox', { name: /港股/ }).click();
    await regionMenu.getByRole('checkbox', { name: /美股/ }).click();
    // Close the menu so the primary action is not occluded on narrow layouts.
    await page.keyboard.press('Escape');
    await expect(regionMenu).toBeHidden();
    await expect(regionTrigger).toContainText(/港股/);
    await expect(regionTrigger).toContainText(/美股/);

    const triggerButton = page.getByRole('button', { name: '大盘复盘', exact: true }).first();
    await expect(triggerButton).toBeEnabled();
    await triggerButton.click();

    await expect.poll(() => submissions).toBe(1);
    expect(capturedRegion).toBe('hk,us');
    expect(capturedNotification).toBe(true);

    // Polling completes immediately under the fixture, so the transient
    // "submitted" notice is often replaced by the completed notice before we assert.
    await expect(page.getByText('大盘复盘已完成')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('大盘复盘任务已完成，结果如下：')).toBeVisible();
    const persistedReport = page.getByTestId('market-review-report');
    await expect(persistedReport.getByText(REGION_PAYLOAD_MARKER, { exact: true })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page).toHaveURL(new RegExp(`${APP_ROUTE_PATHS.researchMarket}\\?recordId=${PERSISTED_REVIEW_ID}`));
    await expect(page.getByText('RAW_STATUS_MUST_NOT_RENDER', { exact: true })).toHaveCount(0);
  });
});

