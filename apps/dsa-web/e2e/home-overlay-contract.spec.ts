// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Locator, type Page, type Route } from '@playwright/test';
import { loginAsE2eAdmin } from './auth-fixture';

const UI_LANGUAGE_STORAGE_KEY = 'dsa.uiLanguage';
const REPORT_A_SUMMARY = 'Contract report A';
const REPORT_B_SUMMARY = 'Contract report B';
const REPORT_C_SUMMARY = 'Contract report C';

const HISTORY_ITEMS = [
  {
    id: 1,
    query_id: 'contract-query-1',
    stock_code: '600519',
    stock_name: 'Moutai',
    report_type: 'detailed',
    sentiment_score: 78,
    operation_advice: 'Watch',
    created_at: '2026-07-14T08:00:00Z',
  },
  {
    id: 2,
    query_id: 'contract-query-2',
    stock_code: 'AAPL',
    stock_name: 'Apple',
    report_type: 'detailed',
    sentiment_score: 72,
    operation_advice: 'Hold',
    created_at: '2026-07-15T08:00:00Z',
  },
];

const COMPLETED_TASK_ITEM = {
  ...HISTORY_ITEMS[0],
  id: 3,
  query_id: 'contract-query-3',
  created_at: '2026-07-16T08:00:00Z',
};

const REPORTS: Record<number, Record<string, unknown>> = {
  1: {
    meta: {
      id: 1,
      query_id: 'contract-query-1',
      stock_code: '600519',
      stock_name: 'Moutai',
      report_type: 'detailed',
      report_language: 'en',
      created_at: '2026-07-14T08:00:00Z',
    },
    summary: {
      analysis_summary: REPORT_A_SUMMARY,
      operation_advice: 'Watch',
      trend_prediction: 'Stable',
      sentiment_score: 78,
    },
  },
  2: {
    meta: {
      id: 2,
      query_id: 'contract-query-2',
      stock_code: 'AAPL',
      stock_name: 'Apple',
      report_type: 'detailed',
      report_language: 'en',
      created_at: '2026-07-15T08:00:00Z',
    },
    summary: {
      analysis_summary: REPORT_B_SUMMARY,
      operation_advice: 'Hold',
      trend_prediction: 'Upward',
      sentiment_score: 72,
    },
  },
  3: {
    meta: {
      id: 3,
      query_id: 'contract-query-3',
      stock_code: '600519',
      stock_name: 'Moutai',
      report_type: 'detailed',
      report_language: 'en',
      created_at: '2026-07-16T08:00:00Z',
    },
    summary: {
      analysis_summary: REPORT_C_SUMMARY,
      operation_advice: 'Watch',
      trend_prediction: 'Upward',
      sentiment_score: 81,
    },
  },
};

function runFlowSnapshot(taskId: string, stockCode: string, stockName: string) {
  return {
    task_id: taskId,
    trace_id: `trace-${taskId}`,
    stock_code: stockCode,
    stock_name: stockName,
    status: 'success',
    generated_at: '2026-07-15T08:01:00Z',
    summary: {
      elapsed_ms: 100,
      failed_attempts: 0,
      fallback_count: 0,
      data_source_count: 0,
      event_count: 0,
    },
    lanes: [{ id: 'entry', label: 'Entry', order: 1 }],
    nodes: [{ id: 'request', lane: 'entry', kind: 'entry', label: 'Request', status: 'success' }],
    edges: [],
    events: [],
  };
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

type HomeApiOptions = {
  delayFirstRecord?: boolean;
  deferCompletedTask?: boolean;
  recordFailure?: {
    recordId: number;
    status: 401 | 403;
    error: 'unauthorized' | 'forbidden';
    message: string;
  };
};

async function installHomeApiFixture(page: Page, options: HomeApiOptions = {}) {
  const delayedRecord = deferred();
  const completedTask = deferred();
  let shouldDelayFirstRecord = Boolean(options.delayFirstRecord);
  let taskEventDelivered = false;
  let fixtureHistoryItems = [...HISTORY_ITEMS];
  const detailRequests: number[] = [];
  const historyRequests: string[] = [];
  const taskFlowRequests: string[] = [];
  const historyFlowRequests: number[] = [];

  await page.route('**/api/v1/system/config/setup/status', (route) => fulfillJson(route, {
    is_complete: true,
    ready_for_smoke: true,
    required_missing_keys: [],
    next_step_key: null,
    checks: [],
  }));
  await page.route('**/api/v1/stocks/watchlist', (route) => fulfillJson(route, { stock_codes: [] }));
  await page.route('**/api/v1/agent/skills', (route) => fulfillJson(route, {
    skills: [],
    default_skill_id: '',
  }));
  await page.route('**/api/v1/analysis/tasks**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/v1/analysis/tasks/stream' && options.deferCompletedTask) {
      if (!taskEventDelivered) {
        await completedTask.promise;
        taskEventDelivered = true;
        fixtureHistoryItems = [COMPLETED_TASK_ITEM, ...fixtureHistoryItems];
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: [
            'event: task_completed',
            `data: ${JSON.stringify({
              task_id: 'task-completed-3',
              stock_code: '600519',
              stock_name: 'Moutai',
              status: 'completed',
              progress: 100,
              report_type: 'detailed',
              created_at: '2026-07-16T08:00:00Z',
              completed_at: '2026-07-16T08:01:00Z',
            })}`,
            '',
            '',
          ].join('\n'),
        });
        return;
      }
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'event: connected\ndata: {}\n\n' });
      return;
    }
    const flowMatch = pathname.match(/^\/api\/v1\/analysis\/tasks\/([^/]+)\/flow$/);
    if (flowMatch) {
      const taskId = decodeURIComponent(flowMatch[1]);
      taskFlowRequests.push(taskId);
      await fulfillJson(route, runFlowSnapshot(taskId, 'AAPL', 'Apple'));
      return;
    }
    if (pathname === '/api/v1/analysis/tasks') {
      await fulfillJson(route, { total: 0, pending: 0, processing: 0, tasks: [] });
      return;
    }
    await route.fallback();
  });
  await page.route('**/api/v1/history**', async (route) => {
    const url = new URL(route.request().url());
    const { pathname } = url;

    if (pathname === '/api/v1/history') {
      historyRequests.push(url.search);
      const reportType = url.searchParams.get('report_type');
      const stockCode = url.searchParams.get('stock_code');
      const items = reportType === 'market_review'
        ? []
        : fixtureHistoryItems.filter((item) => !stockCode || item.stock_code === stockCode);
      await fulfillJson(route, {
        total: items.length,
        page: Number(url.searchParams.get('page') || 1),
        limit: Number(url.searchParams.get('limit') || 20),
        items,
      });
      return;
    }

    if (pathname === '/api/v1/history/stocks') {
      await fulfillJson(route, {
        total: fixtureHistoryItems.length,
        items: fixtureHistoryItems.map((item) => ({
          ...item,
          analysis_count: 1,
          last_analysis_time: item.created_at,
        })),
      });
      return;
    }

    const deleteByCodeMatch = pathname.match(/^\/api\/v1\/history\/by-code\/([^/]+)$/);
    if (route.request().method() === 'DELETE' && deleteByCodeMatch) {
      const stockCode = decodeURIComponent(deleteByCodeMatch[1]);
      const previousLength = fixtureHistoryItems.length;
      fixtureHistoryItems = fixtureHistoryItems.filter((item) => item.stock_code !== stockCode);
      await fulfillJson(route, { deleted: previousLength - fixtureHistoryItems.length });
      return;
    }

    const flowMatch = pathname.match(/^\/api\/v1\/history\/(\d+)\/flow$/);
    if (flowMatch) {
      const recordId = Number(flowMatch[1]);
      historyFlowRequests.push(recordId);
      const item = fixtureHistoryItems.find((candidate) => candidate.id === recordId) ?? HISTORY_ITEMS[0];
      await fulfillJson(
        route,
        runFlowSnapshot(`history-${recordId}`, item.stock_code, item.stock_name),
      );
      return;
    }

    const diagnosticsMatch = pathname.match(/^\/api\/v1\/history\/(\d+)\/diagnostics$/);
    if (diagnosticsMatch) {
      const recordId = Number(diagnosticsMatch[1]);
      const item = fixtureHistoryItems.find((candidate) => candidate.id === recordId) ?? HISTORY_ITEMS[0];
      await fulfillJson(route, {
        trace_id: `trace-record-${recordId}`,
        task_id: `task-record-${recordId}`,
        query_id: `contract-query-${recordId}`,
        stock_code: item.stock_code,
        trigger_source: 'e2e',
        status: 'normal',
        status_label: 'Normal',
        reason: 'Deterministic browser contract fixture',
        components: {},
        copy_text: `trace_id: trace-record-${recordId}`,
      });
      return;
    }

    if (/^\/api\/v1\/history\/\d+\/news$/.test(pathname)) {
      await fulfillJson(route, { total: 0, items: [] });
      return;
    }

    const detailMatch = pathname.match(/^\/api\/v1\/history\/(\d+)$/);
    if (detailMatch) {
      const recordId = Number(detailMatch[1]);
      detailRequests.push(recordId);
      if (recordId === 1 && shouldDelayFirstRecord) {
        shouldDelayFirstRecord = false;
        await delayedRecord.promise;
      }
      if (options.recordFailure?.recordId === recordId) {
        await fulfillJson(route, {
          error: options.recordFailure.error,
          message: options.recordFailure.message,
          params: {},
          details: null,
          detail: null,
        }, options.recordFailure.status);
        return;
      }
      const report = REPORTS[recordId];
      if (report) {
        await fulfillJson(route, report);
      } else {
        await fulfillJson(route, {
          error: 'not_found',
          message: 'The requested report was not found.',
          params: {},
          details: null,
        }, 404);
      }
      return;
    }

    await route.fallback();
  });

  return {
    detailRequests,
    historyRequests,
    taskFlowRequests,
    historyFlowRequests,
    releaseFirstRecord: delayedRecord.resolve,
    releaseCompletedTask: completedTask.resolve,
  };
}

async function openFixtureHome(page: Page, url: string, options: HomeApiOptions = {}) {
  await loginAsE2eAdmin(page);
  // Leave the post-login Home document before installing deterministic Home
  // routes so its in-flight lifecycle requests cannot overlap this scenario.
  await page.goto('/settings');
  await page.waitForLoadState('domcontentloaded');
  await page.evaluate((key) => localStorage.setItem(key, 'en'), UI_LANGUAGE_STORAGE_KEY);
  const fixture = await installHomeApiFixture(page, options);
  await page.goto(url);
  await page.waitForLoadState('domcontentloaded');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  return fixture;
}

async function expectSearchParams(page: Page, expected: Record<string, string | null>) {
  await expect.poll(async () => {
    const url = new URL(page.url());
    return Object.fromEntries(Object.keys(expected).map((key) => [key, url.searchParams.get(key)]));
  }).toEqual(expected);
}

function historyButton(page: Page, name: string, code: string) {
  return page.getByRole('button', { name: new RegExp(`${name} ${code}`) }).first();
}

async function openOverlayFixture(page: Page, width: number) {
  await page.setViewportSize({ width, height: 844 });
  await page.addInitScript((key) => localStorage.setItem(key, 'en'), UI_LANGUAGE_STORAGE_KEY);
  await page.goto('/e2e/overlay-contract-fixture.html');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
}

async function expectFocusWithin(locator: Locator) {
  await expect.poll(() => locator.evaluate((element) => element.contains(document.activeElement))).toBe(true);
}

async function expectBodyOverflow(page: Page, value: string) {
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe(value);
}

async function expectOverlayIsolated(overlay: Locator, isolated: boolean) {
  if (isolated) {
    await expect(overlay).toHaveAttribute('inert', '');
    await expect(overlay).toHaveAttribute('aria-hidden', 'true');
  } else {
    await expect(overlay).not.toHaveAttribute('inert', '');
    await expect(overlay).not.toHaveAttribute('aria-hidden', 'true');
  }
}

test.describe('Settings Help shared overlay contract', () => {
  test('320px Help stays in bounds, traps focus, and restores page state', async ({ page }) => {
    await openOverlayFixture(page, 320);
    await page.evaluate(() => {
      document.body.style.overflow = 'clip';
    });
    const trigger = page.getByRole('button', { name: 'View Standalone help configuration help' });
    const triggerBox = await trigger.boundingBox();
    expect(triggerBox?.width).toBeGreaterThanOrEqual(44);
    expect(triggerBox?.height).toBeGreaterThanOrEqual(44);

    await trigger.click();
    const dialog = page.getByRole('dialog', { name: 'Watchlist' });
    const close = dialog.getByRole('button', { name: 'Close configuration help' });
    await expect(dialog).toBeVisible();
    await expect(page.locator('#root')).toHaveAttribute('inert', '');
    await expect(page.locator('#root')).toHaveAttribute('aria-hidden', 'true');
    await expectBodyOverflow(page, 'hidden');
    await expectFocusWithin(dialog);
    const dialogBox = await dialog.boundingBox();
    expect(dialogBox).not.toBeNull();
    expect(dialogBox!.x).toBeGreaterThanOrEqual(0);
    expect(dialogBox!.x + dialogBox!.width).toBeLessThanOrEqual(320);
    expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    const closeBox = await close.boundingBox();
    expect(closeBox?.width).toBeGreaterThanOrEqual(44);
    expect(closeBox?.height).toBeGreaterThanOrEqual(44);

    await page.keyboard.press('Tab');
    await expectFocusWithin(dialog);
    await close.click();
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expect(page.locator('#root')).not.toHaveAttribute('inert', '');
    await expect(page.locator('#root')).not.toHaveAttribute('aria-hidden', 'true');
    await expectBodyOverflow(page, 'clip');
  });

  test('390px Help closes with Escape and keeps all content horizontally reachable', async ({ page }) => {
    await openOverlayFixture(page, 390);
    const trigger = page.getByRole('button', { name: 'View Standalone help configuration help' });
    await trigger.focus();
    await trigger.click();

    const dialog = page.getByRole('dialog', { name: 'Watchlist' });
    await expect(dialog).toBeVisible();
    await expectFocusWithin(dialog);
    expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.keyboard.press('Escape');

    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expectBodyOverflow(page, '');
  });

  test('Help over Modal closes topmost-first and keeps the lower modal isolated', async ({ page }) => {
    await openOverlayFixture(page, 390);
    const opener = page.getByTestId('open-modal');
    await opener.click();
    const outerDialog = page.getByRole('dialog', { name: 'Outer modal' });
    const outerOverlay = page.locator('[data-overlay-root="modal"]').filter({ hasText: 'Outer modal' });
    const helpTrigger = outerDialog.getByRole('button', { name: 'View Modal help configuration help' });
    await helpTrigger.click();

    const helpDialog = page.getByRole('dialog', { name: 'Watchlist' });
    await expectOverlayIsolated(outerOverlay, true);
    await expectBodyOverflow(page, 'hidden');
    await page.keyboard.press('Escape');

    await expect(helpDialog).toHaveCount(0);
    await expect(outerDialog).toBeVisible();
    await expectOverlayIsolated(outerOverlay, false);
    await expect(helpTrigger).toBeFocused();
    await expectBodyOverflow(page, 'hidden');
    await page.keyboard.press('Escape');

    await expect(outerDialog).toHaveCount(0);
    await expect(opener).toBeFocused();
    await expect(page.locator('#root')).not.toHaveAttribute('inert', '');
    await expectBodyOverflow(page, '');
  });

  test('Help over Drawer closes topmost-first and restores the Drawer trigger', async ({ page }) => {
    await openOverlayFixture(page, 390);
    const opener = page.getByTestId('open-drawer');
    await opener.click();
    const outerDialog = page.getByRole('dialog', { name: 'Outer drawer' });
    const outerOverlay = page.locator('[data-overlay-root="drawer"]');
    const helpTrigger = outerDialog.getByRole('button', { name: 'View Drawer help configuration help' });
    await helpTrigger.click();

    const helpDialog = page.getByRole('dialog', { name: 'Watchlist' });
    await expectOverlayIsolated(outerOverlay, true);
    await page.keyboard.press('Escape');

    await expect(helpDialog).toHaveCount(0);
    await expect(outerDialog).toBeVisible();
    await expectOverlayIsolated(outerOverlay, false);
    await expect(helpTrigger).toBeFocused();
    await expectBodyOverflow(page, 'hidden');
    await page.keyboard.press('Escape');

    await expect(outerDialog).toHaveCount(0);
    await expect(opener).toBeFocused();
    await expectBodyOverflow(page, '');
  });

  test('ConfirmDialog above Help is the only Escape target and restores Help focus', async ({ page }) => {
    await openOverlayFixture(page, 390);
    const opener = page.getByTestId('open-modal');
    await opener.click();
    const outerDialog = page.getByRole('dialog', { name: 'Outer modal' });
    const helpTrigger = outerDialog.getByRole('button', { name: 'View Modal help configuration help' });
    await helpTrigger.click();
    const helpDialog = page.getByRole('dialog', { name: 'Watchlist' });
    const helpOverlay = page.locator('[data-overlay-root="modal"]').filter({ hasText: 'Watchlist' });

    await page.getByTestId('open-confirm').evaluate((element: HTMLElement) => element.click());
    const confirmDialog = page.getByRole('dialog', { name: 'Confirm contract action' });
    await expect(confirmDialog).toBeVisible();
    await expectOverlayIsolated(helpOverlay, true);
    await expectFocusWithin(confirmDialog);
    await page.keyboard.press('Escape');

    await expect(confirmDialog).toHaveCount(0);
    await expect(helpDialog).toBeVisible();
    await expectOverlayIsolated(helpOverlay, false);
    await expectFocusWithin(helpDialog);
    await expectBodyOverflow(page, 'hidden');
    await page.keyboard.press('Escape');

    await expect(helpDialog).toHaveCount(0);
    await expect(outerDialog).toBeVisible();
    await expect(helpTrigger).toBeFocused();
    await expectBodyOverflow(page, 'hidden');
    await page.keyboard.press('Escape');
    await expect(outerDialog).toHaveCount(0);
    await expect(opener).toBeFocused();
    await expectBodyOverflow(page, '');
  });
});

test.describe('Home URL-owned report and Run Flow contract', () => {
  test('report deep link survives refresh and click, Back, and Forward restore selection', async ({ page }) => {
    const fixture = await openFixtureHome(page, '/?keep=yes&recordId=2');
    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toBeVisible();
    await expectSearchParams(page, { keep: 'yes', recordId: '2' });

    await page.reload();
    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toBeVisible();
    await expect.poll(() => fixture.detailRequests.filter((recordId) => recordId === 2).length).toBeGreaterThanOrEqual(2);

    await historyButton(page, 'Moutai', '600519').click();
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();
    await expectSearchParams(page, { keep: 'yes', recordId: '1' });

    const backDetailRequestIndex = fixture.detailRequests.length;
    await page.goBack();
    await expectSearchParams(page, { keep: 'yes', recordId: '2' });
    await expect.poll(() => fixture.detailRequests.slice(backDetailRequestIndex)).toEqual([2]);
    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toBeVisible();

    const forwardDetailRequestIndex = fixture.detailRequests.length;
    await page.goForward();
    await expectSearchParams(page, { keep: 'yes', recordId: '1' });
    await expect.poll(() => fixture.detailRequests.slice(forwardDetailRequestIndex)).toEqual([1]);
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();
  });

  test('a slow report response cannot replace the newer URL selection', async ({ page }) => {
    const fixture = await openFixtureHome(page, '/?recordId=1', { delayFirstRecord: true });
    await expect.poll(() => fixture.detailRequests.includes(1)).toBe(true);
    await historyButton(page, 'Apple', 'AAPL').click();
    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toBeVisible();
    await expectSearchParams(page, { recordId: '2' });

    const staleResponse = page.waitForResponse((response) => (
      new URL(response.url()).pathname === '/api/v1/history/1' && response.status() === 200
    ));
    fixture.releaseFirstRecord();
    await staleResponse;

    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toBeVisible();
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toHaveCount(0);
    await expectSearchParams(page, { recordId: '2' });
  });

  test('task completion replaces the Home URL and opens the completed report', async ({ page }) => {
    const fixture = await openFixtureHome(page, '/?keep=yes&recordId=1', { deferCompletedTask: true });
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();
    const historyLength = await page.evaluate(() => window.history.length);
    const completionRequestIndex = fixture.detailRequests.length;

    fixture.releaseCompletedTask();

    await expect(page.getByText(REPORT_C_SUMMARY, { exact: true })).toBeVisible();
    await expectSearchParams(page, { keep: 'yes', recordId: '3' });
    expect(fixture.detailRequests.slice(completionRequestIndex)).toEqual([3]);
    expect(await page.evaluate(() => window.history.length)).toBe(historyLength);
  });

  test('task completion preserves an explicit report deep link while it is still loading', async ({ page }) => {
    const fixture = await openFixtureHome(page, '/?keep=yes&recordId=1', {
      delayFirstRecord: true,
      deferCompletedTask: true,
    });
    await expect.poll(() => fixture.detailRequests).toEqual([1]);
    const historyRequestCount = fixture.historyRequests.length;

    fixture.releaseCompletedTask();

    await expect.poll(() => fixture.historyRequests.length).toBeGreaterThan(historyRequestCount);
    await expectSearchParams(page, { keep: 'yes', recordId: '1' });
    expect(fixture.detailRequests).toEqual([1]);
    await expect(page.getByText(REPORT_C_SUMMARY, { exact: true })).toHaveCount(0);

    fixture.releaseFirstRecord();
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();
    await expectSearchParams(page, { keep: 'yes', recordId: '1' });
    await expect(page.getByText(REPORT_C_SUMMARY, { exact: true })).toHaveCount(0);
  });

  test('deleting the current report replaces it once without refetching the deleted id', async ({ page }) => {
    const fixture = await openFixtureHome(page, '/?keep=yes&recordId=1');
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();
    const historyLength = await page.evaluate(() => window.history.length);
    const deleteRequestIndex = fixture.detailRequests.length;

    await page.getByRole('button', { name: 'Delete Moutai history record' }).click();
    const confirmDialog = page.getByRole('dialog', { name: 'Delete History' });
    await confirmDialog.getByRole('button', { name: 'Delete', exact: true }).click();

    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toBeVisible();
    await expectSearchParams(page, { keep: 'yes', recordId: '2' });
    expect(fixture.detailRequests.slice(deleteRequestIndex)).toEqual([2]);
    expect(await page.evaluate(() => window.history.length)).toBe(historyLength);
  });

  test('a 401 report deep link keeps its localized error and removes only recordId', async ({ page }) => {
    const fixture = await openFixtureHome(page, '/?keep=yes&recordId=2', {
      recordFailure: {
        recordId: 2,
        status: 401,
        error: 'unauthorized',
        message: 'Server-side authentication diagnostic',
      },
    });

    await expect.poll(() => fixture.detailRequests).toEqual([2]);
    await expect(page.getByRole('alert').filter({ hasText: 'Sign-in required' })).toBeVisible();
    await expectSearchParams(page, { keep: 'yes', recordId: null });
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toHaveCount(0);
    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toHaveCount(0);
  });

  test('a 403 report deep link keeps its localized error and removes only recordId', async ({ page }) => {
    const fixture = await openFixtureHome(page, '/?keep=yes&recordId=2', {
      recordFailure: {
        recordId: 2,
        status: 403,
        error: 'forbidden',
        message: 'Server-side authorization diagnostic',
      },
    });

    await expect.poll(() => fixture.detailRequests).toEqual([2]);
    await expect(page.getByRole('alert').filter({ hasText: 'Request failed' })).toBeVisible();
    await expectSearchParams(page, { keep: 'yes', recordId: null });
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toHaveCount(0);
    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toHaveCount(0);
  });

  test('task Run Flow deep link survives refresh and close preserves report state', async ({ page }) => {
    const fixture = await openFixtureHome(
      page,
      '/?recordId=1&keep=yes&runFlow=task&runFlowTaskId=task-2',
    );
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();
    await expect.poll(() => fixture.taskFlowRequests.filter((taskId) => taskId === 'task-2').length).toBeGreaterThanOrEqual(1);

    await page.reload();
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();
    await expect.poll(() => fixture.taskFlowRequests.filter((taskId) => taskId === 'task-2').length).toBeGreaterThanOrEqual(2);
    await page.getByRole('button', { name: 'Close drawer' }).click();

    await expect(page.getByTestId('run-flow-panel')).toHaveCount(0);
    await expectSearchParams(page, {
      recordId: '1',
      keep: 'yes',
      runFlow: null,
      runFlowTaskId: null,
      runFlowRecordId: null,
    });
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();

    await page.goBack();
    await expectSearchParams(page, {
      recordId: '1',
      keep: 'yes',
      runFlow: 'task',
      runFlowTaskId: 'task-2',
    });
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();
  });

  test('history Run Flow deep link survives refresh and close preserves report state', async ({ page }) => {
    const fixture = await openFixtureHome(
      page,
      '/?recordId=2&keep=yes&runFlow=history&runFlowRecordId=2',
    );
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();
    await expect.poll(() => fixture.historyFlowRequests.filter((recordId) => recordId === 2).length).toBeGreaterThanOrEqual(1);

    await page.reload();
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();
    await expect.poll(() => fixture.historyFlowRequests.filter((recordId) => recordId === 2).length).toBeGreaterThanOrEqual(2);
    await page.getByRole('button', { name: 'Close drawer' }).click();

    await expect(page.getByTestId('run-flow-panel')).toHaveCount(0);
    await expectSearchParams(page, {
      recordId: '2',
      keep: 'yes',
      runFlow: null,
      runFlowTaskId: null,
      runFlowRecordId: null,
    });
    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toBeVisible();

    await page.goBack();
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();
  });

  test('320px history Run Flow Drawer traps focus and restores its trigger on close', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 844 });
    await openFixtureHome(page, '/?recordId=2');
    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toBeVisible();
    await page.getByTestId('run-diagnostics').locator('summary').first().click();
    const trigger = page.getByRole('button', { name: 'View run flow for history record 2' });
    await trigger.click();

    const drawer = page.getByRole('dialog', { name: 'Run Flow' });
    await expect(drawer).toBeVisible();
    await expectFocusWithin(drawer);
    await expect(page.locator('#root')).toHaveAttribute('inert', '');
    await expectBodyOverflow(page, 'hidden');
    await drawer.evaluate(async (element) => {
      await Promise.all(element.getAnimations().map((animation) => animation.finished));
    });
    const drawerBox = await drawer.boundingBox();
    expect(drawerBox).not.toBeNull();
    expect(drawerBox!.x).toBeGreaterThanOrEqual(0);
    expect(drawerBox!.x + drawerBox!.width).toBeLessThanOrEqual(320);
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    await drawer.getByRole('button', { name: 'Close drawer' }).click();

    await expect(drawer).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expectSearchParams(page, { recordId: '2', runFlow: null, runFlowRecordId: null });
    await expect(page.locator('#root')).not.toHaveAttribute('inert', '');
    await expectBodyOverflow(page, '');
  });

  test('390px history Run Flow Drawer closes with Escape and restores its trigger', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openFixtureHome(page, '/?recordId=2');
    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toBeVisible();
    await page.getByTestId('run-diagnostics').locator('summary').first().click();
    const trigger = page.getByRole('button', { name: 'View run flow for history record 2' });
    await trigger.click();

    const drawer = page.getByRole('dialog', { name: 'Run Flow' });
    await expect(drawer).toBeVisible();
    await expectFocusWithin(drawer);
    await page.keyboard.press('Escape');

    await expect(drawer).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expectSearchParams(page, { recordId: '2', runFlow: null, runFlowRecordId: null });
    await expectBodyOverflow(page, '');
  });
});
