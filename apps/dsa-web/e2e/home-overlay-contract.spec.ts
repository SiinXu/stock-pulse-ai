// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Locator, type Page, type Route } from '@playwright/test';
import {
  ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS,
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  RUN_FLOW_ROUTE_QUERY_VALUES,
} from '../src/routing/routes';
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
  watchlistCodes?: string[];
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
  await page.route('**/api/v1/stocks/watchlist', (route) => fulfillJson(route, {
    stock_codes: options.watchlistCodes ?? [],
  }));
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

    if (pathname === '/api/v1/history' && route.request().method() === 'DELETE') {
      const body = route.request().postDataJSON() as { record_ids?: number[] };
      const recordIds = new Set(body.record_ids ?? []);
      const previousLength = fixtureHistoryItems.length;
      fixtureHistoryItems = fixtureHistoryItems.filter((item) => !recordIds.has(item.id));
      await fulfillJson(route, { deleted: previousLength - fixtureHistoryItems.length });
      return;
    }

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
  await page.goto(APP_ROUTE_PATHS.settings);
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

test.describe('Settings Help shared tooltip contract', () => {
  test('320px Help stays in bounds without isolating the page', async ({ page }) => {
    await openOverlayFixture(page, 320);
    await page.evaluate(() => {
      document.body.style.overflow = 'clip';
    });
    const trigger = page.getByRole('button', { name: 'View Standalone help configuration help' });
    const triggerBox = await trigger.boundingBox();
    expect(triggerBox?.width).toBeGreaterThanOrEqual(44);
    expect(triggerBox?.height).toBeGreaterThanOrEqual(44);

    await trigger.click();
    const tooltip = page.getByRole('tooltip');
    await expect(tooltip).toBeVisible();
    await expect(page.locator('#root')).not.toHaveAttribute('inert', '');
    await expect(page.locator('#root')).not.toHaveAttribute('aria-hidden', 'true');
    await expectBodyOverflow(page, 'clip');
    const tooltipBox = await tooltip.boundingBox();
    expect(tooltipBox).not.toBeNull();
    expect(tooltipBox!.x).toBeGreaterThanOrEqual(0);
    expect(tooltipBox!.x + tooltipBox!.width).toBeLessThanOrEqual(320);
    expect(await tooltip.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);

    await page.keyboard.press('Escape');
    await expect(tooltip).toHaveCount(0);
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

    const tooltip = page.getByRole('tooltip');
    await expect(tooltip).toBeVisible();
    expect(await tooltip.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.keyboard.press('Escape');

    await expect(tooltip).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expectBodyOverflow(page, '');
  });

  test('Tooltip and sibling Popover preserve topmost Escape and outside-press ownership', async ({ page }) => {
    await openOverlayFixture(page, 390);
    await page.getByTestId('open-popover').click();
    const menu = page.getByRole('menu', { name: 'Fixture actions' });
    const menuItem = page.getByRole('menuitem', { name: 'Fixture action' });
    const helpTrigger = page.getByRole('button', { name: 'View Standalone help configuration help' });
    await expect(menu).toBeVisible();
    await helpTrigger.hover();
    await expect(page.getByRole('tooltip')).toBeVisible();
    await expect(menuItem).toBeFocused();

    await page.keyboard.press('Escape');

    await expect(page.getByRole('tooltip')).toHaveCount(0);
    await expect(menu).toBeVisible();
    await page.getByTestId('open-popover').hover();
    await helpTrigger.hover();
    await expect(page.getByRole('tooltip')).toBeVisible();
    await helpTrigger.click();
    await expect(menu).toHaveCount(0);
  });

  test('Tooltip interaction inside an owned nested Popover preserves both menus', async ({ page }) => {
    await openOverlayFixture(page, 390);
    await page.getByTestId('open-popover').click();
    const outerMenu = page.getByRole('menu', { name: 'Fixture actions', exact: true });
    await outerMenu.getByRole('menuitem', { name: 'Open nested actions' }).click();
    const innerMenu = page.getByRole('menu', { name: 'Nested fixture actions', exact: true });
    const helpTrigger = innerMenu.getByRole('button', {
      name: 'View Nested help configuration help',
    });
    await helpTrigger.hover();
    await expect(page.getByRole('tooltip')).toBeVisible();

    await helpTrigger.click();

    await expect(outerMenu).toBeVisible();
    await expect(innerMenu).toBeVisible();
  });

  test('Help over Modal closes without closing or isolating the modal', async ({ page }) => {
    await openOverlayFixture(page, 390);
    const opener = page.getByTestId('open-modal');
    await opener.click();
    const outerDialog = page.getByRole('dialog', { name: 'Outer modal' });
    const outerOverlay = page.locator('[data-overlay-root="modal"]').filter({ hasText: 'Outer modal' });
    const helpTrigger = outerDialog.getByRole('button', { name: 'View Modal help configuration help' });
    await helpTrigger.click();

    const helpTooltip = page.getByRole('tooltip');
    await expect(helpTooltip).toBeVisible();
    await expectOverlayIsolated(outerOverlay, false);
    await expectBodyOverflow(page, 'hidden');
    await page.keyboard.press('Escape');

    await expect(helpTooltip).toHaveCount(0);
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

  test('hovered Help consumes Escape while another Modal control owns focus', async ({ page }) => {
    await openOverlayFixture(page, 390);
    const opener = page.getByTestId('open-modal');
    await opener.click();
    const outerDialog = page.getByRole('dialog', { name: 'Outer modal' });
    const focusedControl = outerDialog.getByTestId('open-confirm');
    const helpTrigger = outerDialog.getByRole('button', { name: 'View Modal help configuration help' });
    await focusedControl.focus();
    await helpTrigger.hover();
    await expect(page.getByRole('tooltip')).toBeVisible();

    await page.keyboard.press('Escape');

    await expect(page.getByRole('tooltip')).toHaveCount(0);
    await expect(outerDialog).toBeVisible();
    await expect(focusedControl).toBeFocused();
    await expectBodyOverflow(page, 'hidden');
    await page.keyboard.press('Escape');
    await expect(outerDialog).toHaveCount(0);
    await expect(opener).toBeFocused();
  });

  test('Help over Drawer closes without closing or isolating the drawer', async ({ page }) => {
    await openOverlayFixture(page, 390);
    const opener = page.getByTestId('open-drawer');
    await opener.click();
    const outerDialog = page.getByRole('dialog', { name: 'Outer drawer' });
    const outerOverlay = page.locator('[data-overlay-root="drawer"]');
    const helpTrigger = outerDialog.getByRole('button', { name: 'View Drawer help configuration help' });
    await helpTrigger.click();

    const helpTooltip = page.getByRole('tooltip');
    await expect(helpTooltip).toBeVisible();
    await expectOverlayIsolated(outerOverlay, false);
    await page.keyboard.press('Escape');

    await expect(helpTooltip).toHaveCount(0);
    await expect(outerDialog).toBeVisible();
    await expectOverlayIsolated(outerOverlay, false);
    await expect(helpTrigger).toBeFocused();
    await expectBodyOverflow(page, 'hidden');
    await page.keyboard.press('Escape');

    await expect(outerDialog).toHaveCount(0);
    await expect(opener).toBeFocused();
    await expectBodyOverflow(page, '');
  });

  test('Detail Drawer exposes semantic slots and stays within its desktop width tier', async ({ page }) => {
    await openOverlayFixture(page, 1280);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const opener = page.getByTestId('open-drawer');
    await opener.click();
    const drawer = page.getByRole('dialog', { name: 'Outer drawer' });
    await expect(drawer).toBeVisible();
    await expect(drawer).toHaveAttribute('data-drawer-variant', 'detail');
    await expect(drawer).toHaveAttribute('data-drawer-side', 'right');
    await expect(drawer).toHaveAttribute('data-drawer-size', 'default');
    await expect(drawer.locator('[data-overlay-slot="header"]')).toContainText('Outer drawer');
    await expect(drawer.locator('[data-overlay-slot="body"]')).toContainText('Open confirmation');
    const maxAnimationDuration = await drawer.evaluate((element) => Math.max(
      0,
      ...element.getAnimations().map((animation) => {
        const duration = animation.effect?.getComputedTiming().duration;
        return typeof duration === 'number' ? duration : Number.POSITIVE_INFINITY;
      }),
    ));
    expect(maxAnimationDuration).toBeLessThanOrEqual(1);
    await drawer.evaluate(async (element) => {
      await Promise.all(element.getAnimations().map((animation) => animation.finished));
    });
    const drawerBox = await drawer.boundingBox();
    expect(drawerBox).not.toBeNull();
    expect(Math.round(drawerBox!.width)).toBe(576);
    await drawer.getByRole('button', { name: 'Close drawer' }).click();
    await expect(drawer).toHaveCount(0);
    await expect(opener).toBeFocused();
  });

  test('ConfirmDialog above Help remains the only Escape target and restores Help focus', async ({ page }) => {
    await openOverlayFixture(page, 390);
    const opener = page.getByTestId('open-modal');
    await opener.click();
    const outerDialog = page.getByRole('dialog', { name: 'Outer modal' });
    const helpTrigger = outerDialog.getByRole('button', { name: 'View Modal help configuration help' });
    const helpPopupTrigger = helpTrigger.locator('xpath=..');
    // Keep this focus-restoration scenario keyboard-only. A pointer left over
    // the trigger can legitimately reopen the hover tooltip after an overlay
    // is removed, adding another topmost Escape target on some browsers.
    await helpTrigger.focus();
    await expect(page.getByRole('tooltip')).toBeVisible();
    await expect(helpPopupTrigger).toHaveAttribute('data-dialog-popup', 'true');

    await page.getByTestId('open-confirm').evaluate((element: HTMLElement) => element.click());
    const confirmDialog = page.getByRole('dialog', { name: 'Confirm contract action' });
    await expect(confirmDialog).toBeVisible();
    await expect(page.getByRole('tooltip')).toHaveCount(0);
    await expectFocusWithin(confirmDialog);
    await page.keyboard.press('Escape');

    await expect(confirmDialog).toHaveCount(0);
    await expect(outerDialog).toBeVisible();
    await expect(helpTrigger).toBeFocused();
    const restoredTooltip = page.getByRole('tooltip');
    await expect(restoredTooltip).toBeVisible();
    await expect(helpPopupTrigger).toHaveAttribute('data-dialog-popup', 'true');
    await expectBodyOverflow(page, 'hidden');
    await page.keyboard.press('Escape');

    await expect(restoredTooltip).toHaveCount(0);
    await expect(helpPopupTrigger).not.toHaveAttribute('data-dialog-popup', 'true');
    await expect(outerDialog).toBeVisible();
    await expect(helpTrigger).toBeFocused();
    await expectBodyOverflow(page, 'hidden');
    await page.keyboard.press('Escape');
    await expect(outerDialog).toHaveCount(0);
    await expect(opener).toBeFocused();
    await expectBodyOverflow(page, '');
  });
});

test.describe('Legacy Home redirect and Analysis Workbench URL-owned contract', () => {
  test('legacy Home report and Run Flow state redirects to the canonical Workbench segment', async ({ page }) => {
    await openFixtureHome(
      page,
      '/?keep=yes&recordId=2&stock=AAPL&workspace=history&runFlow=history&runFlowRecordId=2#evidence',
    );

    await expect.poll(() => new URL(page.url()).pathname).toBe(APP_ROUTE_PATHS.researchAnalysis);
    await expectSearchParams(page, {
      keep: 'yes',
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId]: '2',
      stock: 'AAPL',
      workspace: null,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow]: RUN_FLOW_ROUTE_QUERY_VALUES.history,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId]: '2',
    });
    await expect(page).toHaveURL(/#evidence$/);
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();
    await expect(page.getByRole('dialog', { name: 'Run Flow' })).toHaveAttribute(
      'data-drawer-variant',
      'detail',
    );
  });

  test('390px history trend keeps the fixed table inside its own scroll region', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openFixtureHome(page, `${APP_ROUTE_PATHS.researchAnalysis}?segment=history&recordId=1`);
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'History trend' }).click();

    const table = page.getByRole('table', { name: 'Historical analysis records' });
    const scrollRegion = page.getByRole('region', { name: 'Historical analysis records' });
    await expect(table).toHaveAttribute('data-layout', 'fixed');
    await expect(table).toHaveClass(/(?:^|\s)min-w-\[64rem\](?:\s|$)/);
    const dimensions = await scrollRegion.evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      left: element.getBoundingClientRect().left,
      right: element.getBoundingClientRect().right,
    }));
    expect(dimensions.scrollWidth).toBeGreaterThan(dimensions.clientWidth);
    expect(dimensions.left).toBeGreaterThanOrEqual(0);
    expect(dimensions.right).toBeLessThanOrEqual(391);
    expect(await page.evaluate(() => document.documentElement.scrollWidth))
      .toBeLessThanOrEqual(await page.evaluate(() => document.documentElement.clientWidth + 1));
  });

  test('report deep link survives refresh and click, Back, and Forward restore selection', async ({ page }) => {
    const fixture = await openFixtureHome(
      page,
      `${APP_ROUTE_PATHS.researchAnalysis}?keep=yes&segment=history&recordId=2`,
    );
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

  test('legacy stock and workspace context normalizes into the Workbench after refresh', async ({ page }) => {
    await openFixtureHome(page, '/?recordId=1&stock=00700.HK&workspace=watchlist&keep=yes');

    await expect.poll(() => new URL(page.url()).pathname).toBe(APP_ROUTE_PATHS.researchAnalysis);
    await expectSearchParams(page, {
      segment: 'history',
      recordId: '1',
      stock: 'HK00700',
      workspace: null,
      keep: 'yes',
    });
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();

    await page.reload();
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();
    await expectSearchParams(page, { segment: 'history', recordId: '1', stock: 'HK00700' });
  });

  test('bare Home navigation does not restore the last Workbench report context', async ({ page }) => {
    await openFixtureHome(
      page,
      `${APP_ROUTE_PATHS.researchAnalysis}?segment=history&recordId=1&stock=00700.HK`,
    );
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();
    await expect.poll(() => page.evaluate(() => (
      window.sessionStorage.getItem('dsa.web.sessionContinuity.v1') ?? ''
    ))).toContain('HK00700');

    await page.goto('/');

    await expect.poll(() => new URL(page.url()).pathname).toBe(APP_ROUTE_PATHS.home);
    await expectSearchParams(page, { recordId: null, stock: null, workspace: null });
    await expect(page.getByTestId('home-core-blocks').getByRole('region')).toHaveCount(3);
  });

  test('logout clears persisted workflow traces but retains UI preferences', async ({ page }) => {
    await openFixtureHome(page, `${APP_ROUTE_PATHS.researchAnalysis}?stock=AAPL`);
    await page.goto('/chat?session=session-private&stock=AAPL&recordId=1');
    await expect(page.getByRole('heading', { name: 'Ask Stock' })).toBeVisible();
    await page.evaluate(() => {
      window.sessionStorage.setItem('dsa_chat_session_id', 'session-private');
      window.sessionStorage.setItem('dsa_research_run:session-private', '{"question":"private"}');
      window.sessionStorage.setItem('dsa.alphasift.activeScreenTask.v1', '{"taskId":"private"}');
      window.localStorage.setItem('dsa_chat_session_id', 'legacy-private');
      window.localStorage.setItem('dsa_research_run:legacy-private', '{"question":"legacy"}');
    });

    await page.getByRole('button', { name: 'Log out' }).click();
    const dialog = page.getByRole('dialog', { name: 'Log out' });
    await dialog.getByRole('button', { name: 'Log out' }).click();

    await expect.poll(() => {
      const url = new URL(page.url());
      return { pathname: url.pathname, search: url.search };
    }).toEqual({ pathname: '/login', search: '' });
    expect(await page.evaluate(() => ({
      sessionKeys: Object.keys(window.sessionStorage).filter((key) => (
        key === 'dsa.web.sessionContinuity.v1'
        || key === 'dsa_chat_session_id'
        || key === 'dsa.alphasift.activeScreenTask.v1'
        || key.startsWith('dsa_research_run:')
      )),
      legacyChat: window.localStorage.getItem('dsa_chat_session_id'),
      legacyResearch: window.localStorage.getItem('dsa_research_run:legacy-private'),
      language: window.localStorage.getItem('dsa.uiLanguage'),
    }))).toEqual({
      sessionKeys: [],
      legacyChat: null,
      legacyResearch: null,
      language: 'en',
    });

    await loginAsE2eAdmin(page);
    await expect(page).toHaveURL('/');
  });

  test('a slow report response cannot replace the newer URL selection', async ({ page }) => {
    const fixture = await openFixtureHome(
      page,
      `${APP_ROUTE_PATHS.researchAnalysis}?segment=history&recordId=1`,
      { delayFirstRecord: true },
    );
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

  test('task completion offers the completed Workbench report without replacing explicit history', async ({ page }) => {
    const fixture = await openFixtureHome(
      page,
      `${APP_ROUTE_PATHS.researchAnalysis}?keep=yes&segment=history&recordId=1`,
      { deferCompletedTask: true },
    );
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();
    const historyLength = await page.evaluate(() => window.history.length);
    const completionRequestIndex = fixture.detailRequests.length;

    fixture.releaseCompletedTask();

    await expect(page.getByText('Analysis completed', { exact: true })).toBeVisible();
    await expectSearchParams(page, { keep: 'yes', segment: 'history', recordId: '1' });
    await page.getByRole('button', { name: 'View report' }).click();
    await expect(page.getByText(REPORT_C_SUMMARY, { exact: true })).toBeVisible();
    await expectSearchParams(page, { keep: 'yes', segment: 'history', recordId: '3' });
    expect(fixture.detailRequests.slice(completionRequestIndex)).toEqual([3]);
    expect(await page.evaluate(() => window.history.length)).toBe(historyLength + 1);
  });

  test('task completion preserves an explicit report deep link while it is still loading', async ({ page }) => {
    const fixture = await openFixtureHome(page, `${APP_ROUTE_PATHS.researchAnalysis}?keep=yes&segment=history&recordId=1`, {
      delayFirstRecord: true,
      deferCompletedTask: true,
    });
    await expect.poll(() => fixture.detailRequests.length).toBeGreaterThan(0);
    const historyRequestCount = fixture.historyRequests.length;

    fixture.releaseCompletedTask();

    await expect.poll(() => fixture.historyRequests.length).toBeGreaterThan(historyRequestCount);
    await expectSearchParams(page, { keep: 'yes', recordId: '1' });
    expect(fixture.detailRequests).not.toContain(3);
    await expect(page.getByText(REPORT_C_SUMMARY, { exact: true })).toHaveCount(0);

    fixture.releaseFirstRecord();
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();
    await expectSearchParams(page, { keep: 'yes', recordId: '1' });
    await expect(page.getByText(REPORT_C_SUMMARY, { exact: true })).toHaveCount(0);
  });

  test('deleting the current report replaces it once without refetching the deleted id', async ({ page }) => {
    const fixture = await openFixtureHome(
      page,
      `${APP_ROUTE_PATHS.researchAnalysis}?keep=yes&segment=history&recordId=1`,
    );
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();
    const historyLength = await page.evaluate(() => window.history.length);
    const deleteRequestIndex = fixture.detailRequests.length;

    await page.getByRole('checkbox', { name: 'Select Moutai history record' }).click();
    await page.getByRole('button', { name: 'Delete', exact: true }).click();
    await page.getByRole('dialog', { name: 'Delete History' })
      .getByRole('button', { name: 'Delete', exact: true })
      .click();

    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toBeVisible();
    await expectSearchParams(page, { keep: 'yes', recordId: '2' });
    expect(fixture.detailRequests.slice(deleteRequestIndex)).toEqual([2]);
    expect(await page.evaluate(() => window.history.length)).toBe(historyLength);
  });

  test('a 401 report deep link keeps its localized error and removes only recordId', async ({ page }) => {
    const fixture = await openFixtureHome(page, `${APP_ROUTE_PATHS.researchAnalysis}?keep=yes&segment=history&recordId=2`, {
      recordFailure: {
        recordId: 2,
        status: 401,
        error: 'unauthorized',
        message: 'Server-side authentication diagnostic',
      },
    });

    await expect.poll(() => fixture.detailRequests.length).toBeGreaterThan(0);
    expect(fixture.detailRequests.every((recordId) => recordId === 2)).toBe(true);
    await expect(page.getByRole('alert').filter({ hasText: 'Sign-in required' })).toBeVisible();
    await expectSearchParams(page, { keep: 'yes', recordId: null });
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toHaveCount(0);
    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toHaveCount(0);
  });

  test('a 403 report deep link keeps its localized error and removes only recordId', async ({ page }) => {
    const fixture = await openFixtureHome(page, `${APP_ROUTE_PATHS.researchAnalysis}?keep=yes&segment=history&recordId=2`, {
      recordFailure: {
        recordId: 2,
        status: 403,
        error: 'forbidden',
        message: 'Server-side authorization diagnostic',
      },
    });

    await expect.poll(() => fixture.detailRequests.length).toBeGreaterThan(0);
    expect(fixture.detailRequests.every((recordId) => recordId === 2)).toBe(true);
    await expect(page.getByRole('alert').filter({ hasText: 'Request failed' })).toBeVisible();
    await expectSearchParams(page, { keep: 'yes', recordId: null });
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toHaveCount(0);
    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toHaveCount(0);
  });

  test('task Run Flow deep link survives refresh and close preserves the tasks segment', async ({ page }) => {
    const fixture = await openFixtureHome(
      page,
      `${APP_ROUTE_PATHS.researchAnalysis}?segment=tasks&keep=yes&runFlow=task&runFlowTaskId=task-2`,
    );
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();
    const runFlowDrawer = page.getByRole('dialog', { name: 'Run Flow' });
    await expect(runFlowDrawer).toHaveAttribute('data-drawer-variant', 'detail');
    await expect(runFlowDrawer).toHaveAttribute('data-drawer-size', 'wide');
    await expect.poll(() => fixture.taskFlowRequests.filter((taskId) => taskId === 'task-2').length).toBeGreaterThanOrEqual(1);

    await page.reload();
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();
    await expect.poll(() => fixture.taskFlowRequests.filter((taskId) => taskId === 'task-2').length).toBeGreaterThanOrEqual(2);
    await runFlowDrawer.getByRole('button', { name: 'Close drawer', exact: true }).click();

    await expect(page.getByTestId('run-flow-panel')).toHaveCount(0);
    await expectSearchParams(page, {
      segment: 'tasks',
      recordId: null,
      keep: 'yes',
      runFlow: null,
      runFlowTaskId: null,
      runFlowRecordId: null,
    });
    await expect(page.getByText('No running tasks', { exact: true })).toBeVisible();

  });

  test('history Run Flow deep link survives refresh and close preserves report state', async ({ page }) => {
    const fixture = await openFixtureHome(
      page,
      `${APP_ROUTE_PATHS.researchAnalysis}?segment=history&recordId=2&keep=yes&runFlow=history&runFlowRecordId=2`,
    );
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();
    await expect.poll(() => fixture.historyFlowRequests.filter((recordId) => recordId === 2).length).toBeGreaterThanOrEqual(1);

    await page.reload();
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();
    await expect.poll(() => fixture.historyFlowRequests.filter((recordId) => recordId === 2).length).toBeGreaterThanOrEqual(2);
    await page.getByRole('dialog', { name: 'Run Flow' })
      .getByRole('button', { name: 'Close drawer', exact: true })
      .click();

    await expect(page.getByTestId('run-flow-panel')).toHaveCount(0);
    await expectSearchParams(page, {
      recordId: '2',
      keep: 'yes',
      runFlow: null,
      runFlowTaskId: null,
      runFlowRecordId: null,
    });
    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toBeVisible();

  });

  test('active Workbench Run Flow survives a major-view round trip in the current tab', async ({ page }) => {
    await openFixtureHome(
      page,
      `${APP_ROUTE_PATHS.researchAnalysis}?segment=history&recordId=2&stock=AAPL&runFlow=history&runFlowRecordId=2`,
    );
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();

    await page.goto('/chat?stock=AAPL');
    const workbenchLink = page.locator(`nav a[href*="${APP_ROUTE_PATHS.researchAnalysis}"][href*="runFlow=history"]`);
    await expect(workbenchLink).toHaveCount(1);
    await workbenchLink.click();

    await expectSearchParams(page, {
      segment: 'history',
      recordId: '2',
      stock: 'AAPL',
      runFlow: 'history',
      runFlowRecordId: '2',
    });
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();
  });

  test('320px history Run Flow Drawer traps focus and restores its trigger on close', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 844 });
    await openFixtureHome(page, `${APP_ROUTE_PATHS.researchAnalysis}?segment=history&recordId=2`);
    await expect(page.getByText(REPORT_B_SUMMARY, { exact: true })).toBeVisible();
    await page.getByTestId('run-diagnostics').locator('summary').first().click();
    const trigger = page.getByRole('button', { name: 'View run flow for history record 2' });
    await trigger.click();

    const drawer = page.getByRole('dialog', { name: 'Run Flow' });
    await expect(drawer).toBeVisible();
    await expect(drawer).toHaveAttribute('data-drawer-variant', 'detail');
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
    await drawer.getByRole('button', { name: 'Close drawer', exact: true }).click();

    await expect(drawer).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expectSearchParams(page, { recordId: '2', runFlow: null, runFlowRecordId: null });
    await expect(page.locator('#root')).not.toHaveAttribute('inert', '');
    await expectBodyOverflow(page, '');
  });

  test('390px history Run Flow Drawer closes with Escape and restores its trigger', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openFixtureHome(page, `${APP_ROUTE_PATHS.researchAnalysis}?segment=history&recordId=2`);
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

test.describe('Analysis Workbench interaction contract', () => {
  test('three URL segments keep history selection and Run Flow on one page', async ({ page }) => {
    const fixture = await openFixtureHome(page, APP_ROUTE_PATHS.home);

    await page.getByRole('link', { name: 'Analysis Workbench' }).click();
    const heading = page.getByRole('heading', { name: 'Analysis Workbench' });
    await expect(heading).toBeVisible();
    await expect(heading).toBeFocused();
    const tabs = page.getByRole('tablist', { name: 'Analysis Workbench segments' });
    await expect(tabs.getByRole('tab')).toHaveText([
      'Launch & batch',
      'Running tasks',
      'History & comparison',
    ]);

    await tabs.getByRole('tab', { name: 'Running tasks' }).click();
    await expectSearchParams(page, {
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
    });
    await expect(page.getByText('No running tasks', { exact: true })).toBeVisible();

    await tabs.getByRole('tab', { name: 'History & comparison' }).click();
    await expectSearchParams(page, {
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId]: '1',
    });
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();
    await expect.poll(() => fixture.detailRequests).toContain(1);

    await page.getByRole('button', { name: 'History trend' }).click();
    await expect(page.getByRole('heading', { name: 'History trend' })).toBeVisible();
    await expect(page.getByRole('table', { name: 'Historical analysis records' })).toBeVisible();
    await page.getByRole('button', { name: 'Back to current report' }).click();
    await expect(page.getByText(REPORT_A_SUMMARY, { exact: true })).toBeVisible();

    await page.getByTestId('run-diagnostics').locator('summary').first().click();
    await page.getByRole('button', { name: 'View run flow for history record 1' }).click();
    await expect(page.getByTestId('run-flow-panel')).toBeVisible();
    await expectSearchParams(page, {
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId]: '1',
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow]: RUN_FLOW_ROUTE_QUERY_VALUES.history,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId]: '1',
    });
  });

  test('an accepted launch switches directly to the tasks segment', async ({ page }) => {
    await openFixtureHome(page, APP_ROUTE_PATHS.researchAnalysis);
    let submitted: Record<string, unknown> | null = null;
    await page.route('**/api/v1/analysis/analyze', async (route) => {
      submitted = route.request().postDataJSON() as Record<string, unknown>;
      await fulfillJson(route, {
        task_id: 'workbench-e2e-task',
        status: 'pending',
      }, 202);
    });

    await page.locator('#analysis-workbench-stock-search').fill('AAPL');
    await page.getByRole('button', { name: 'Analyze', exact: true }).last().click();

    await expectSearchParams(page, {
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
    });
    await expect(page.getByText('AAPL', { exact: true }).first()).toBeVisible();
    expect(submitted).toMatchObject({
      stock_code: 'AAPL',
      async_mode: true,
      report_type: 'detailed',
    });
  });

  test('pending-only batch submits watchlist symbols without today coverage', async ({ page }) => {
    await openFixtureHome(page, APP_ROUTE_PATHS.researchAnalysis, {
      watchlistCodes: ['AAPL'],
    });
    let submitted: Record<string, unknown> | null = null;
    await page.route('**/api/v1/analysis/analyze', async (route) => {
      submitted = route.request().postDataJSON() as Record<string, unknown>;
      await fulfillJson(route, {
        accepted: [{ task_id: 'workbench-pending-task', stock_code: 'AAPL', status: 'pending' }],
        duplicates: [],
        message: 'Accepted',
      }, 202);
    });

    const pendingButton = page.getByRole('button', { name: 'Pending only' });
    await expect(pendingButton).toBeEnabled();
    await pendingButton.click();

    await expectSearchParams(page, {
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
    });
    expect(submitted).toMatchObject({
      stock_codes: ['AAPL'],
      async_mode: true,
      report_type: 'detailed',
    });
  });
});
