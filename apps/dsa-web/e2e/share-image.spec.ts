// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Page, type Route } from '@playwright/test';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  buildAnalysisWorkbenchHref,
} from '../src/routing/routes';
import { loginAsE2eAdmin, mockCompletedSetupStatus } from './auth-fixture';

test.use({ locale: 'zh-CN' });

const UI_LANGUAGE_STORAGE_KEY = 'dsa.uiLanguage';

/** Minimal valid 1×1 PNG — keeps success path free of real renderers. */
const FIXTURE_PNG_BYTES = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);

async function login(page: Page) {
  await page.addInitScript((storageKey) => {
    window.localStorage.setItem(storageKey, 'zh');
  }, UI_LANGUAGE_STORAGE_KEY);
  await mockCompletedSetupStatus(page);
  await loginAsE2eAdmin(page);
  await expect(page.getByTestId('home-core-blocks')).toBeVisible({ timeout: 10_000 });
}

async function openSeededHistoryReport(page: Page) {
  await page.goto(buildAnalysisWorkbenchHref({
    segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
  }));
  await expect(page.getByRole('heading', { name: '分析工作台' })).toBeVisible({ timeout: 10_000 });
  const firstHistoryItem = page.locator('.history-item[data-control="pressable"]').first();
  await expect(firstHistoryItem).toBeVisible({ timeout: 10_000 });
  await expect(firstHistoryItem).toContainText('E2E Fixture');
  await firstHistoryItem.click();
  const shareButton = page.getByRole('button', { name: '分享' });
  await expect(shareButton).toBeVisible({ timeout: 10_000 });
  return shareButton;
}

/**
 * Force the renderer-unavailable 503 path through the e2e route fixture.
 * Avoids installing/removing host renderers (wkhtml / m2f / Chromium CLI).
 */
async function fulfillShareImageUnavailable(route: Route) {
  await route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({
      error: 'share_image_unavailable',
      message: (
        '分享图片生成失败，请检查 playwright 转图工具是否已安装并可用。'
        + ' playwright 引擎需要: cd apps/dsa-web && npm ci && npx playwright install chromium'
      ),
    }),
  });
}

async function fulfillShareImagePng(route: Route) {
  await route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: FIXTURE_PNG_BYTES,
    headers: {
      'Content-Disposition': 'attachment; filename="stockpulse-report-e2e.png"',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}

test.describe('Share image', () => {
  test('downloads a generated PNG and surfaces the success state', async ({ page }) => {
    await page.route('**/api/v1/history/*/share-image', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await fulfillShareImagePng(route);
    });

    await login(page);
    const shareButton = await openSeededHistoryReport(page);

    const shareResponse = page.waitForResponse((response) => (
      response.url().includes('/share-image')
      && response.request().method() === 'GET'
      && response.status() === 200
    ));
    await shareButton.click();
    await shareResponse;

    // Headless Chromium typically lacks canShare({ files }), so the button falls
    // through to the DOM download path and ends in the success label.
    // If native share prep is available, the ready label is also acceptable.
    await expect(page.getByRole('button', {
      name: /已生成|再次点击分享/,
    })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('share-image-error')).toHaveCount(0);
  });

  test('surfaces renderer-unavailable 503 in the share-image error region', async ({ page }) => {
    await page.route('**/api/v1/history/*/share-image', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await fulfillShareImageUnavailable(route);
    });

    await login(page);
    const shareButton = await openSeededHistoryReport(page);

    const shareResponse = page.waitForResponse((response) => (
      response.url().includes('/share-image')
      && response.request().method() === 'GET'
      && response.status() === 503
    ));
    await shareButton.click();
    const response = await shareResponse;
    expect(response.status()).toBe(503);
    expect(await response.json()).toMatchObject({ error: 'share_image_unavailable' });

    // The button must leave idle and present the error + retry affordance.
    // Note: axios attaches a pre-rehydration ParsedApiError for blob 503s before
    // history.getShareImage rehydrates the envelope, so the visible copy may be the
    // generic 503 network message until that product path is fixed. Unit tests cover
    // the share_image_unavailable localization contract for the rehydrated envelope.
    const errorRegion = page.getByTestId('share-image-error');
    await expect(errorRegion).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: '重试' }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: '分享', exact: true })).toHaveCount(0);
  });
});

