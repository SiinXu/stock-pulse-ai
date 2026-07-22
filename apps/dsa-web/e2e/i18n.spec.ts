// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Page } from '@playwright/test';
import { UI_TEXT } from '../src/i18n/uiText';
import { ALERT_PAGE_TEXT } from '../src/locales/alerts';
import { BACKTEST_TEXT } from '../src/locales/backtest';
import { PORTFOLIO_TEXT } from '../src/locales/portfolio';
import { SCREENING_TEXT } from '../src/locales/screening';
import { loginAsE2eAdmin, getE2eAuthStatus } from './auth-fixture';
import { UI_LANGUAGE_METADATA, type UiLanguage } from '../src/i18n/uiLanguages';
import {
  APP_ROUTE_PATHS,
  SETTINGS_SECTION_IDS,
  buildSettingsHref,
  buildSettingsSectionHref,
} from '../src/routing/routes';

const fakeProviderPort = Number(process.env.DSA_WEB_SMOKE_PROVIDER_PORT || 18101);
const BUILT_IN_PROVIDER_LABELS = {
  openai: { zh: 'OpenAI 官方', en: 'OpenAI Official' },
  gemini: { zh: 'Gemini 官方', en: 'Gemini Official' },
  ollama: { zh: 'Ollama（本地）', en: 'Ollama (Local)' },
  custom: { zh: '自定义兼容服务', en: 'Custom compatible service' },
} as const;
const CHINESE_SCRIPT = /[\u3400-\u9fff]/;
const usageSettingsHref = buildSettingsSectionHref(SETTINGS_SECTION_IDS.usage);
const HOME_NAV_LABELS: Record<UiLanguage, string> = {
  zh: '首页',
  'zh-TW': '首頁',
  en: 'Home',
  ja: 'ホーム',
  ko: '홈',
  de: 'Startseite',
  es: 'Inicio',
  ms: 'Laman Utama',
  fr: 'Accueil',
  id: 'Beranda',
};
const STOCK_LIST_FIELD_LABELS: Record<Exclude<UiLanguage, 'zh' | 'en'>, string> = {
  'zh-TW': '自選股列表',
  ja: '選択銘柄リスト',
  ko: '선정된 종목 목록',
  de: 'Liste ausgewählter Aktien',
  es: 'Lista de acciones seleccionadas',
  ms: 'Senarai saham terpilih',
  fr: 'Liste des actions sélectionnées',
  id: 'Daftar saham pilihan',
};

const uiLanguageSelector = (page: Page) =>
  page.locator('[data-testid="ui-language-selector"]:visible [role="combobox"]').first();

async function openProfileMenu(page: Page) {
  const trigger = page.getByRole('button', { name: 'StockPulse', exact: true }).last();
  await expect(trigger).toBeVisible();
  if (await trigger.getAttribute('aria-expanded') !== 'true') {
    await trigger.click();
  }
}

async function selectUiLanguage(page: Page, language: UiLanguage) {
  let selector = uiLanguageSelector(page);
  if (!await selector.isVisible().catch(() => false)) {
    await openProfileMenu(page);
    selector = uiLanguageSelector(page);
  }
  await expect(selector).toBeVisible();
  await selector.click();
  await page.locator(`[role="option"][data-value="${language}"]`).click();
}

async function switchToEnglish(page: Page) {
  await selectUiLanguage(page, 'en');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
}

async function assertUiLanguage(page: Page, language: UiLanguage) {
  await selectUiLanguage(page, language);
  await expect(page.locator('html')).toHaveAttribute('lang', UI_LANGUAGE_METADATA[language].htmlLang);
  await expect(page.getByRole('link', { name: HOME_NAV_LABELS[language], exact: true }).first()).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('dsa.uiLanguage'))).toBe(language);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', UI_LANGUAGE_METADATA[language].htmlLang);
  if (!await uiLanguageSelector(page).isVisible().catch(() => false)) {
    await openProfileMenu(page);
  }
  await expect(uiLanguageSelector(page)).toHaveAttribute('data-value', language);
  await expect(page.getByRole('link', { name: HOME_NAV_LABELS[language], exact: true }).first()).toBeVisible();
}

async function assertLocalizedStockListField(
  page: Page,
  language: keyof typeof STOCK_LIST_FIELD_LABELS,
) {
  await page.goto(buildSettingsHref({ section: 'overview', view: 'readiness' }));
  await expect(page.locator('html')).toHaveAttribute('lang', UI_LANGUAGE_METADATA[language].htmlLang);
  await expect(page.getByLabel(STOCK_LIST_FIELD_LABELS[language], { exact: true })).toBeVisible();
  await expect(page.getByLabel('Stock List', { exact: true })).toHaveCount(0);
}

async function loginInEnglish(page: Page) {
  await loginAsE2eAdmin(page);
  await switchToEnglish(page);
}

test.describe('complete UI i18n acceptance', () => {
  test('initialization, switching, persistence, history, mobile navigation, and theme remain localized', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN'); // 1
    await switchToEnglish(page); // 2
    await expect(page.getByRole('link', { name: 'Home' })).toBeVisible(); // 3
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible(); // 4
    await expect(uiLanguageSelector(page)).toBeVisible(); // 5
    expect(await page.evaluate(() => localStorage.getItem('dsa.uiLanguage'))).toBe('en'); // 6

    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en'); // 7
    await page.getByRole('link', { name: 'Agent' }).click();
    await page.goBack();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en'); // 8
    await page.goForward();
    await expect(page.getByText(UI_TEXT.en['chat.title'], { exact: true }).first()).toBeVisible(); // 9

    await page.setViewportSize({ width: 390, height: 844 });
    const openNavigation = page.getByRole('button', { name: /Open navigation|Menu/i });
    if (await openNavigation.isVisible().catch(() => false)) await openNavigation.click();
    const mobileBacktestLink = page.getByRole('link', { name: 'Backtest' });
    await expect(mobileBacktestLink).toBeVisible(); // 10
    await mobileBacktestLink.click();

    const themeToggle = page.getByRole('button', { name: 'Toggle theme' }).first();
    if (!await themeToggle.isVisible().catch(() => false)) {
      await openProfileMenu(page);
    }
    await themeToggle.click();
    await page.getByRole('menuitemradio', { name: 'Dark', exact: true }).click();
    await expect(page.locator('html')).toHaveClass(/dark/); // 11

    await selectUiLanguage(page, 'zh');
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN'); // 12
  });

  test('Traditional Chinese selection persists with localized navigation and Settings field titles', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await assertUiLanguage(page, 'zh-TW');
    await assertLocalizedStockListField(page, 'zh-TW');
  });

  test('Japanese selection persists with localized navigation and Settings field titles', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await assertUiLanguage(page, 'ja');
    await assertLocalizedStockListField(page, 'ja');
  });

  test('Korean selection persists with localized navigation and Settings field titles', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await assertUiLanguage(page, 'ko');
    await assertLocalizedStockListField(page, 'ko');
  });

  test('German selection persists with localized navigation and Settings field titles', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await assertUiLanguage(page, 'de');
    await assertLocalizedStockListField(page, 'de');
  });

  test('Spanish selection persists with localized navigation and Settings field titles', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await assertUiLanguage(page, 'es');
    await assertLocalizedStockListField(page, 'es');
  });

  test('Malay selection persists with localized navigation and Settings field titles', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await assertUiLanguage(page, 'ms');
    await assertLocalizedStockListField(page, 'ms');
  });

  test('French selection persists with localized navigation and Settings field titles', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await assertUiLanguage(page, 'fr');
    await assertLocalizedStockListField(page, 'fr');
  });

  test('Indonesian selection persists with localized navigation and Settings field titles', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await assertUiLanguage(page, 'id');
    await assertLocalizedStockListField(page, 'id');
  });

  test('login supports English for both first setup and returning admin states', async ({ page }) => {
    const status = await getE2eAuthStatus(page);
    await page.addInitScript(() => localStorage.setItem('dsa.uiLanguage', 'en'));
    await page.goto('/login');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en'); // 13
    await expect(page.getByRole('heading', { name: status.passwordSet ? 'Admin login' : 'Set initial password' })).toBeVisible(); // 14
    await expect(page.getByRole('button', { name: status.passwordSet ? 'Enter workspace' : 'Finish setup and sign in' })).toBeVisible(); // 15
  });

  test('every first-level route renders English chrome and an English document title', async ({ page }) => {
    await loginInEnglish(page);
    const routes = [
      { path: APP_ROUTE_PATHS.home, text: UI_TEXT.en['home.analyze'], title: UI_TEXT.en['home.pageTitle'] },
      { path: APP_ROUTE_PATHS.agent, text: UI_TEXT.en['chat.title'], title: UI_TEXT.en['chat.pageTitle'] },
      { path: APP_ROUTE_PATHS.researchMarket, text: UI_TEXT.en['home.marketReview'], title: UI_TEXT.en['home.marketReviewPageTitle'] },
      { path: APP_ROUTE_PATHS.researchDiscover, text: SCREENING_TEXT.en.title, title: SCREENING_TEXT.en.documentTitle },
      { path: APP_ROUTE_PATHS.portfolio, text: PORTFOLIO_TEXT.en.title, title: PORTFOLIO_TEXT.en.documentTitle },
      { path: APP_ROUTE_PATHS.decisionSignals, text: UI_TEXT.en['decisionSignals.title'], title: UI_TEXT.en['decisionSignals.pageTitle'] },
      { path: APP_ROUTE_PATHS.researchBacktest, text: BACKTEST_TEXT.en.runBacktest, title: BACKTEST_TEXT.en.documentTitle },
      { path: APP_ROUTE_PATHS.alerts, text: ALERT_PAGE_TEXT.en.title, title: ALERT_PAGE_TEXT.en.documentTitle },
      { path: usageSettingsHref, text: UI_TEXT.en['usage.title'], title: UI_TEXT.en['usage.title'] },
      { path: APP_ROUTE_PATHS.settings, text: UI_TEXT.en['settings.pageTitle'], title: UI_TEXT.en['settings.pageTitle'] },
      { path: '/missing-i18n-route', text: UI_TEXT.en['notFound.title'], title: UI_TEXT.en['notFound.pageTitle'] },
    ];

    for (const route of routes) {
      await page.goto(route.path);
      await expect(page.getByText(route.text, { exact: true }).first()).toBeVisible({ timeout: 15_000 });
      await expect(page).toHaveTitle(new RegExp(route.title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'));
    }
    expect(routes).toHaveLength(11); // 16-26
  });

  test('English Settings localizes model access, discovery success, and discovery failure', async ({ page }) => {
    await loginInEnglish(page);
    await page.goto(buildSettingsHref({ section: 'ai_models', view: 'connections' }));
    await expect(page.getByRole('heading', { name: 'Model access' })).toBeVisible({ timeout: 15_000 }); // 26
    await page.getByRole('button', { name: /Add model service/ }).first().click();
    const dialog = page.getByRole('dialog', { name: 'Add model service' });
    await expect(dialog).toBeVisible(); // 27
    await dialog.getByLabel('Choose model provider').click();
    await page.locator('[role="option"][data-value="custom"]').click();
    await dialog.getByRole('button', { name: 'Next' }).click();
    await dialog.getByLabel('Connection name').fill(`i18n_${Date.now()}`);
    await dialog.getByLabel('Base URL').fill(`http://127.0.0.1:${fakeProviderPort}/v1`);
    await dialog.getByRole('button', { name: 'Get models' }).click();
    await expect(dialog.getByText('Found 3 models')).toBeVisible({ timeout: 20_000 }); // 28

    await dialog.getByLabel('Base URL').fill(`http://127.0.0.1:${fakeProviderPort}/missing`);
    await dialog.getByRole('button', { name: 'Get models' }).click();
    await expect(dialog.getByText(/Model discovery|failed|Request/i).last()).toBeVisible({ timeout: 20_000 }); // 29
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeVisible(); // 30
  });

  test('English Connection Modal renders all built-in Provider labels without Chinese script', async ({ page }) => {
    await loginInEnglish(page);
    await page.goto(buildSettingsHref({ section: 'ai_models', view: 'connections' }));
    await expect(page.getByRole('heading', { name: 'Model access' })).toBeVisible({ timeout: 15_000 });
    await page.getByRole('button', { name: /Add model service/ }).first().click();
    const dialog = page.getByRole('dialog', { name: 'Add model service' });
    await dialog.getByLabel('Choose model provider').click();

    for (const [providerId, labels] of Object.entries(BUILT_IN_PROVIDER_LABELS)) {
      const option = dialog.locator(`[role="option"][data-value="${providerId}"]`);
      await expect(option).toContainText(labels.en);
      expect(await option.innerText()).not.toMatch(CHINESE_SCRIPT);
    }
  });

  test('Chinese Connection Modal renders the localized built-in Provider labels', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await page.goto(buildSettingsHref({ section: 'ai_models', view: 'connections' }));
    await expect(page.getByRole('heading', { name: '模型接入' })).toBeVisible({ timeout: 15_000 });
    await page.getByRole('button', { name: /添加模型服务/ }).first().click();
    const dialog = page.getByRole('dialog', { name: '添加模型服务' });
    await dialog.getByLabel('选择模型服务商').click();

    for (const [providerId, labels] of Object.entries(BUILT_IN_PROVIDER_LABELS)) {
      await expect(dialog.locator(`[role="option"][data-value="${providerId}"]`)).toContainText(labels.zh);
    }
  });

  test('Connection Modal opens in the language selected from Profile', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await page.goto(buildSettingsHref({ section: 'ai_models', view: 'connections' }));
    await selectUiLanguage(page, 'en');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.getByRole('heading', { name: 'Model access' })).toBeVisible({ timeout: 15_000 });
    await page.getByRole('button', { name: /Add model service/ }).first().click();
    const dialog = page.getByRole('dialog', { name: 'Add model service' });
    const localizedSelect = dialog.getByLabel('Choose model provider');
    await localizedSelect.click();
    await dialog.locator('[role="option"][data-value="openai"]').click();
    await expect(localizedSelect).toHaveAttribute('data-value', 'openai');
    await expect(localizedSelect).toContainText('OpenAI Official');
    await localizedSelect.click();
    const openAiOption = dialog.locator('[role="option"][data-value="openai"]');
    await expect(openAiOption).toContainText('OpenAI Official');
    expect(await openAiOption.innerText()).not.toMatch(CHINESE_SCRIPT);
  });

  test('English First-run Wizard uses catalog-localized Provider labels', async ({ page }) => {
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
    await loginInEnglish(page);
    await page.goto(buildSettingsHref({ section: 'base', view: 'base' }));
    await page.getByRole('button', { name: 'Start wizard' }).click();
    const dialog = page.getByRole('dialog', { name: 'Quick setup wizard' });
    await dialog.getByRole('button', { name: /Cloud API/ }).click();
    await dialog.getByRole('button', { name: 'Next' }).click();
    await dialog.getByRole('combobox', { name: 'Provider' }).click();

    for (const [providerId, labels] of Object.entries(BUILT_IN_PROVIDER_LABELS)) {
      const option = page.locator(`[role="option"][data-value="${providerId}"]`);
      await expect(option).toContainText(labels.en);
      expect(await option.innerText()).not.toMatch(CHINESE_SCRIPT);
    }
  });

  test('a Chinese server diagnostic is not the primary English error', async ({ page }) => {
    await page.route('**/api/v1/system/config/llm/available-models**', async (route) => {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'catalog_unavailable', message: '中文原始诊断' }) });
    });
    await loginInEnglish(page);
    await page.goto(buildSettingsHref({ section: 'ai_models', view: 'overview' }));
    await expect(page.getByText('Failed to load available models')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('中文原始诊断', { exact: true })).toHaveCount(0);
  });
});
