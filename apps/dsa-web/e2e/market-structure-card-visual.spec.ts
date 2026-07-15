import {
  chromium,
  expect,
  test,
  type Browser,
  type Page,
  type TestInfo,
} from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer as createViteServer, type ViteDevServer } from 'vite';

/**
 * Visual regression / integration smoke for MarketStructureCard on the REAL
 * application page path (not a standalone fixture page):
 *
 *   HomePage -> ReportSummary (market_review early-return)
 *            -> MarketReviewReportView -> MarketStructureCard
 *
 * The real dsa-web app is served by a programmatically started Vite dev
 * server (using the repo's own vite.config.ts). All `/api/v1/**` requests are
 * intercepted with Playwright route mocks so the flow exercises the actual
 * store/report pipeline: history list auto-select -> history detail with
 * `details.market_structure` -> camelCase conversion -> card render.
 *
 * Coverage: light/dark themes x desktop(1280x900)/mobile(390x844) viewports,
 * with per-scenario screenshots attached as Playwright artifacts.
 */

test.use({ locale: 'zh-CN' });

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(currentDir, '..');

const MARKET_REVIEW_RECORD_ID = 101;
const CARD_REGION_NAME = '题材主线与个股位置';

// ---------------------------------------------------------------------------
// Wire-format mocks. History endpoints return snake_case JSON exactly like the
// FastAPI backend; the frontend converts them with camelcase-keys (deep).
// ---------------------------------------------------------------------------

const marketStructureContextMock = {
  schema_version: 'market-structure-v1',
  status: 'partial',
  market: 'cn',
  trade_date: '2026-07-04',
  market_theme_context: {
    schema_version: 'market-theme-v1',
    status: 'partial',
    market: 'cn',
    active_themes: [
      { name: '机器人概念', change_pct: 4.2, rank: 1, source: 'concept', phase: 'accelerating' },
      { name: 'AI 算力', change_pct: 3.6, rank: 2, source: 'concept', phase: 'warming' },
    ],
    leading_concepts: [
      { name: '机器人概念', change_pct: 4.2, rank: 1, source: 'concept' },
      { name: 'AI 算力', change_pct: 3.6, rank: 2, source: 'concept' },
    ],
    leading_industries: [
      { name: '通用设备', change_pct: 2.1, rank: 2, source: 'industry' },
      { name: '软件开发', change_pct: 1.8, rank: 4, source: 'industry' },
    ],
    lagging_themes: [],
    theme_breadth: {
      active_count: 2,
      leading_concept_count: 2,
      leading_industry_count: 2,
      lagging_count: 0,
    },
    data_quality: {
      status: 'partial',
      missing_fields: ['industry_rankings'],
      sources: [],
      errors: [],
    },
  },
  stock_market_position: {
    schema_version: 'stock-market-position-v1',
    status: 'partial',
    stock_code: '300024',
    stock_name: '机器人',
    market: 'cn',
    primary_theme: {
      name: '机器人概念',
      source: 'concept',
      phase: 'accelerating',
      rank: 1,
      change_pct: 4.2,
    },
    related_boards: [
      { name: '机器人概念', type: '概念', source: 'concept', rank: 1, change_pct: 4.2 },
      { name: '通用设备', type: '行业', source: 'industry', rank: 2, change_pct: 2.1 },
    ],
    stock_role: 'follower',
    theme_phase: 'accelerating',
    risk_tags: [
      { code: 'theme_data_partial', message: '题材主线数据不完整' },
    ],
    missing_fields: ['hotspot_constituents'],
  },
};

const marketReviewMarkdownMock = [
  '# A股市场复盘',
  '',
  '## 市场概览',
  '',
  '两市成交额约 1.9 万亿元，题材热度集中在机器人与 AI 算力方向。',
].join('\n');

const historyDetailMock = {
  meta: {
    id: MARKET_REVIEW_RECORD_ID,
    query_id: 'mock-market-review',
    stock_code: 'MARKET',
    stock_name: 'A股市场复盘',
    report_type: 'market_review',
    report_language: 'zh',
    model_used: 'mock-model',
    created_at: '2026-07-04T16:10:00+08:00',
  },
  summary: {
    analysis_summary: '市场缩量整理，题材集中在机器人与 AI 算力。',
    trend_prediction: '震荡',
    sentiment_score: 60,
    operation_advice: '观望',
  },
  strategy: {},
  details: {
    context_snapshot: {
      market_review_payload: {
        version: 1,
        kind: 'market_review',
        region: 'cn',
        language: 'zh',
        title: 'A股市场复盘',
        date: '2026-07-04',
        sections: [
          {
            key: 'overview',
            title: '市场概览',
            markdown: '两市成交额约 1.9 万亿元，题材热度集中在机器人与 AI 算力方向。',
          },
        ],
        markdown_report: marketReviewMarkdownMock,
      },
    },
    market_structure: marketStructureContextMock,
  },
};

const historyListMock = {
  total: 1,
  page: 1,
  limit: 20,
  items: [
    {
      id: MARKET_REVIEW_RECORD_ID,
      query_id: 'mock-market-review',
      stock_code: 'MARKET',
      stock_name: 'A股市场复盘',
      report_type: 'market_review',
      trend_prediction: '震荡',
      analysis_summary: '市场缩量整理，题材集中在机器人与 AI 算力。',
      sentiment_score: 60,
      operation_advice: '观望',
      model_used: 'mock-model',
      created_at: '2026-07-04T16:10:00+08:00',
    },
  ],
};

// auth/status is consumed as-is (no camelCase conversion on the client).
const authStatusMock = {
  authEnabled: false,
  loggedIn: true,
  passwordSet: false,
  passwordChangeable: false,
  setupState: 'no_password',
};

const setupStatusMock = {
  is_complete: true,
  ready_for_smoke: true,
  required_missing_keys: [],
  next_step_key: null,
  checks: [],
};

async function installApiMocks(page: Page): Promise<void> {
  await page.route('**/api/v1/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    const fulfillJson = (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (pathname === '/api/v1/auth/status') {
      return fulfillJson(authStatusMock);
    }
    if (pathname === '/api/v1/analysis/tasks/stream') {
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: ': mock stream\n\n',
      });
    }
    if (pathname === '/api/v1/analysis/tasks') {
      return fulfillJson({ total: 0, pending: 0, processing: 0, tasks: [] });
    }
    if (pathname === '/api/v1/agent/skills') {
      return fulfillJson({ skills: [], default_skill_id: '' });
    }
    if (pathname === '/api/v1/system/config/setup/status') {
      return fulfillJson(setupStatusMock);
    }
    if (pathname === '/api/v1/stocks/watchlist') {
      return fulfillJson({ stock_codes: [] });
    }
    if (pathname === '/api/v1/history/stocks') {
      return fulfillJson({ total: 0, items: [] });
    }
    if (pathname === `/api/v1/history/${MARKET_REVIEW_RECORD_ID}/markdown`) {
      return fulfillJson({ content: marketReviewMarkdownMock });
    }
    if (pathname === `/api/v1/history/${MARKET_REVIEW_RECORD_ID}/news`) {
      return fulfillJson({ total: 0, items: [] });
    }
    if (pathname === `/api/v1/history/${MARKET_REVIEW_RECORD_ID}`) {
      return fulfillJson(historyDetailMock);
    }
    if (pathname === '/api/v1/history') {
      return fulfillJson(historyListMock);
    }
    // Safe empty fallback for anything else the dashboard touches on mount.
    return fulfillJson({});
  });
}

interface Scenario {
  id: string;
  theme: 'light' | 'dark';
  viewport: { width: number; height: number };
}

const SCENARIOS: Scenario[] = [
  { id: 'light-desktop', theme: 'light', viewport: { width: 1280, height: 900 } },
  { id: 'dark-desktop', theme: 'dark', viewport: { width: 1280, height: 900 } },
  { id: 'light-mobile-390', theme: 'light', viewport: { width: 390, height: 844 } },
  { id: 'dark-mobile-390', theme: 'dark', viewport: { width: 390, height: 844 } },
];

async function attachScreenshots(page: Page, scenario: Scenario, testInfo: TestInfo): Promise<void> {
  const card = page.getByRole('region', { name: CARD_REGION_NAME });
  await card.scrollIntoViewIfNeeded();

  const cardShotPath = testInfo.outputPath(`market-structure-card-${scenario.id}.png`);
  const cardShot = await card.screenshot({ path: cardShotPath });
  expect(cardShot.length).toBeGreaterThan(1024);
  await testInfo.attach(`market-structure-card-${scenario.id}`, {
    path: cardShotPath,
    contentType: 'image/png',
  });

  const pageShotPath = testInfo.outputPath(`home-market-review-${scenario.id}.png`);
  await page.screenshot({ path: pageShotPath, fullPage: false });
  await testInfo.attach(`home-market-review-${scenario.id}`, {
    path: pageShotPath,
    contentType: 'image/png',
  });
}

test.describe('MarketStructureCard on the real market review page', () => {
  let browser: Browser | null = null;
  let viteServer: ViteDevServer | null = null;
  let appUrl = '';

  test.beforeAll(async () => {
    browser = await chromium.launch();

    viteServer = await createViteServer({
      configFile: path.join(webRoot, 'vite.config.ts'),
      root: webRoot,
      logLevel: 'error',
      server: {
        host: '127.0.0.1',
        port: 0,
        strictPort: false,
        hmr: false,
        open: false,
      },
    });
    await viteServer.listen();
    const address = viteServer.httpServer?.address();
    if (!address || typeof address === 'string') {
      throw new Error('Vite dev server did not expose a network address');
    }
    appUrl = `http://127.0.0.1:${address.port}/`;
  });

  test.afterAll(async () => {
    if (viteServer) {
      await viteServer.close();
      viteServer = null;
    }
    if (browser) {
      await browser.close();
      browser = null;
    }
  });

  for (const scenario of SCENARIOS) {
    test(`renders inside MarketReviewReportView (${scenario.id})`, async ({ browser: _unused }, testInfo) => {
      void _unused;
      test.setTimeout(180_000);

      const context = await browser!.newContext({
        locale: 'zh-CN',
        viewport: scenario.viewport,
        colorScheme: scenario.theme,
      });
      try {
        await context.addInitScript(({ theme }) => {
          window.localStorage.setItem('theme', theme);
          window.localStorage.setItem('dsa.uiLanguage', 'zh');
        }, { theme: scenario.theme });

        const page = await context.newPage();
        await installApiMocks(page);
        await page.goto(appUrl, { waitUntil: 'domcontentloaded' });

        // The real chain must complete: history list auto-select -> detail
        // fetch -> MarketReviewReportView -> MarketStructureCard section.
        const card = page.getByRole('region', { name: CARD_REGION_NAME });
        await expect(card).toBeVisible({ timeout: 90_000 });
        await expect(card.getByText('大盘题材层')).toBeVisible();
        await expect(card.getByText('个股位置层')).toBeVisible();
        await expect(card.getByText(/机器人概念/).first()).toBeVisible();
        await expect(card.getByText('题材主线数据不完整')).toBeVisible();

        // Theme really applied by next-themes (class strategy on <html>).
        const isDark = await page.evaluate(() => document.documentElement.classList.contains('dark'));
        expect(isDark).toBe(scenario.theme === 'dark');

        await attachScreenshots(page, scenario, testInfo);
      } finally {
        await context.close();
      }
    });
  }

  test('legacy market review reports without marketStructure render without the card', async ({ browser: _unused }, testInfo) => {
    void _unused;
    void testInfo;
    test.setTimeout(180_000);

    const context = await browser!.newContext({
      locale: 'zh-CN',
      viewport: { width: 1280, height: 900 },
      colorScheme: 'light',
    });
    try {
      await context.addInitScript(() => {
        window.localStorage.setItem('theme', 'light');
        window.localStorage.setItem('dsa.uiLanguage', 'zh');
      });

      const page = await context.newPage();
      await installApiMocks(page);
      // Override only the detail endpoint with a legacy payload (no
      // details.market_structure field), like reports created before this
      // feature existed.
      await page.route(`**/api/v1/history/${MARKET_REVIEW_RECORD_ID}`, async (route) => {
        const legacyDetail = {
          ...historyDetailMock,
          details: {
            context_snapshot: historyDetailMock.details.context_snapshot,
          },
        };
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(legacyDetail),
        });
      });
      await page.goto(appUrl, { waitUntil: 'domcontentloaded' });

      // The market review report itself renders...
      await expect(page.getByText('市场概览').first()).toBeVisible({ timeout: 90_000 });
      // ...but the market-structure card stays hidden and nothing crashes.
      await expect(page.getByRole('region', { name: CARD_REGION_NAME })).toHaveCount(0);
    } finally {
      await context.close();
    }
  });
});
