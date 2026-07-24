// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Locator, type Page } from '@playwright/test';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  buildAnalysisWorkbenchHref,
} from '../src/routing/routes';
import { loginAsE2eAdmin } from './auth-fixture';

const buttonHeights: Record<string, number> = {
  compact: 20,
  default: 24,
  comfortable: 28,
  primary: 32,
};

const iconButtonHeights: Record<string, number> = {
  compact: 28,
  default: 32,
  comfortable: 36,
  navigation: 44,
};

const inputHeights: Record<string, number> = {
  default: 32,
  comfortable: 36,
  primary: 40,
};

const minimumCoarseTarget = 44;
const pixelRoundingTolerance = 0.01;

async function expectNoHorizontalOverflow(page: Page, label: string): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    viewportWidth: document.documentElement.clientWidth,
    pageWidth: document.documentElement.scrollWidth,
  }));
  expect(
    dimensions.pageWidth,
    `${label} page width ${dimensions.pageWidth}px exceeds ${dimensions.viewportWidth}px`,
  ).toBeLessThanOrEqual(dimensions.viewportWidth + 1);
}

async function setTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((nextTheme) => localStorage.setItem('theme', nextTheme), theme);
  await page.reload();
  await expect(page.locator('html')).toHaveClass(new RegExp(`(?:^|\\s)${theme}(?:\\s|$)`));
}

async function expectVisibleHeights(
  locator: Locator,
  expectedBySize: Record<string, number>,
): Promise<void> {
  const samples = await locator.evaluateAll((elements) => elements
    .filter((element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
    })
    .map((element) => ({
      label: element.getAttribute('aria-label') || element.textContent?.trim() || element.tagName,
      size: element.getAttribute('data-size') || '',
      height: element.getBoundingClientRect().height,
      radius: Number.parseFloat(getComputedStyle(element).borderRadius),
    })));

  expect(samples.length, 'expected at least one visible shared control').toBeGreaterThan(0);
  for (const sample of samples) {
    const expectedHeight = expectedBySize[sample.size];
    expect(expectedHeight, `unknown semantic size ${sample.size} on ${sample.label}`).toBeDefined();
    expect(sample.height, `${sample.label} should use the ${sample.size} visible tier`).toBeCloseTo(
      expectedHeight,
      0,
    );
    expect(sample.radius, `${sample.label} must not be pill-shaped`).toBeLessThan(sample.height / 2);
  }
}

async function expectCoarseHitTarget(locator: Locator, label: string): Promise<void> {
  const target = await locator.evaluate((element) => {
    const pseudo = getComputedStyle(element, '::after');
    return {
      width: Number.parseFloat(pseudo.width),
      height: Number.parseFloat(pseudo.height),
    };
  });
  expect(target.width, `${label} coarse-pointer width`)
    .toBeGreaterThanOrEqual(minimumCoarseTarget - pixelRoundingTolerance);
  expect(target.height, `${label} coarse-pointer height`)
    .toBeGreaterThanOrEqual(minimumCoarseTarget - pixelRoundingTolerance);
}

test.describe('touch-capable foundation controls', () => {
  test.use({ hasTouch: true });

  test('separates visible density from touch targets and keeps keyboard feedback', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/login');
    await setTheme(page, 'light');
    await expect(page.getByRole('heading', { name: 'StockPulse', exact: true })).toBeVisible();
    await page.evaluate(() => Promise.all(
      document.getAnimations().map((animation) => animation.finished),
    ));
    expect(await page.evaluate(() => matchMedia('(any-pointer: coarse)').matches)).toBe(true);

    const password = page.locator('#password');
    await expectVisibleHeights(password, inputHeights);
    const passwordFrame = password.locator('..');
    expect(await passwordFrame.evaluate((element) => element.getBoundingClientRect().height))
      .toBeGreaterThanOrEqual(minimumCoarseTarget - pixelRoundingTolerance);

    const passwordToggle = passwordFrame.getByRole('button');
    await expect(passwordToggle).toHaveAccessibleName('显示内容');
    await expectVisibleHeights(passwordToggle, iconButtonHeights);
    await expectCoarseHitTarget(passwordToggle, 'password visibility action');

    const passwordBox = await password.boundingBox();
    const passwordFrameBox = await passwordFrame.boundingBox();
    expect(passwordBox).not.toBeNull();
    expect(passwordFrameBox).not.toBeNull();
    await passwordToggle.focus();
    const topFrameGap = passwordBox!.y - passwordFrameBox!.y;
    const bottomFrameGap = passwordFrameBox!.y + passwordFrameBox!.height
      - passwordBox!.y - passwordBox!.height;
    expect(Math.max(topFrameGap, bottomFrameGap)).toBeGreaterThan(0);
    const frameHitPoint = {
      x: passwordBox!.x + passwordBox!.width / 2,
      y: topFrameGap > bottomFrameGap
        ? passwordFrameBox!.y + topFrameGap / 2
        : passwordBox!.y + passwordBox!.height + bottomFrameGap / 2,
    };
    expect(await page.evaluate(({ x, y }) => {
      const input = document.querySelector('#password');
      return document.elementFromPoint(x, y) === input?.parentElement;
    }, frameHitPoint)).toBe(true);
    await page.touchscreen.tap(frameHitPoint.x, frameHitPoint.y);
    await expect(password).toBeFocused();

    const passwordToggleBox = await passwordToggle.boundingBox();
    expect(passwordToggleBox).not.toBeNull();
    await page.touchscreen.tap(
      passwordToggleBox!.x + passwordToggleBox!.width / 2,
      passwordToggleBox!.y - 2,
    );
    await expect(password).toHaveAttribute('type', 'text');
    await passwordToggle.click();
    await expect(password).toHaveAttribute('type', 'password');

    const submit = page.getByRole('button', { name: /授权进入工作台|完成设置并登录/ });
    await expectVisibleHeights(submit, buttonHeights);
    await expectCoarseHitTarget(submit, 'login submit');

    await loginAsE2eAdmin(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
    }));
    const historySelection = page.getByRole('checkbox', {
      name: /选择 .*历史记录|Select .* history record/,
    }).first();
    await expect(historySelection).toBeVisible();
    const historySelectionTarget = historySelection.locator('xpath=ancestor::label[1]');
    const historySelectionTargetBox = await historySelectionTarget.boundingBox();
    expect(historySelectionTargetBox).not.toBeNull();
    expect(historySelectionTargetBox!.width).toBeGreaterThanOrEqual(
      minimumCoarseTarget - pixelRoundingTolerance,
    );
    expect(historySelectionTargetBox!.height).toBeGreaterThanOrEqual(
      minimumCoarseTarget - pixelRoundingTolerance,
    );
    await historySelection.check();

    const historyDelete = page.getByRole('button', { name: /删除|Delete/, exact: true }).first();
    await expect(historyDelete).toBeVisible();
    await expectVisibleHeights(historyDelete, buttonHeights);
    await expectCoarseHitTarget(historyDelete, 'history delete action');
    await historyDelete.click();
    const deleteDialog = page.getByRole('dialog', { name: '删除历史记录' });
    await expect(deleteDialog).toBeVisible();
    await deleteDialog.getByRole('button', { name: '取消' }).click();
    await expect(deleteDialog).toHaveCount(0);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(APP_ROUTE_PATHS.researchBacktest);
    await expect(page.locator('[data-control="input"]:visible').first()).toBeVisible();
    await expectVisibleHeights(page.locator('[data-control="input"]:visible'), inputHeights);
    await expectVisibleHeights(page.locator('[data-control="button"]:visible'), buttonHeights);

    await page.getByRole('button', { name: /打开.*日历/ }).first().click();
    const iconButton = page.locator('[data-control="icon-button"]:visible').first();
    await expect(iconButton).toBeVisible();
    await expectVisibleHeights(page.locator('[data-control="icon-button"]:visible'), iconButtonHeights);
    await expectCoarseHitTarget(iconButton, 'icon action');

    await iconButton.focus();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Tab');
    await expect(iconButton).toBeFocused();
    const focusShadow = await iconButton.evaluate((element) => getComputedStyle(element).boxShadow);
    expect(focusShadow).not.toBe('none');

    const accessibleName = await iconButton.getAttribute('aria-label');
    expect(accessibleName).toBeTruthy();
    const tooltip = page.getByRole('tooltip');
    await expect(tooltip).toHaveText(accessibleName || '');
    const tooltipId = await tooltip.getAttribute('id');
    expect(tooltipId).toBeTruthy();
    await expect(iconButton).toHaveAttribute('aria-describedby', tooltipId || '');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('tooltip')).toHaveCount(0);

    await expectNoHorizontalOverflow(page, 'coarse-pointer backtest 390x844');
  });
});
