// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Locator, type Page } from '@playwright/test';
import { loginAsE2eAdmin } from './auth-fixture';

const buttonHeights: Record<string, number> = {
  compact: 28,
  default: 32,
  comfortable: 36,
  primary: 40,
  xsm: 28,
  sm: 32,
  md: 36,
  lg: 40,
  xl: 40,
};

const iconButtonHeights: Record<string, number> = {
  compact: 28,
  default: 32,
  comfortable: 36,
};

const inputHeights: Record<string, number> = {
  default: 32,
  comfortable: 36,
  primary: 40,
};

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
  expect(target.width, `${label} coarse-pointer width`).toBeGreaterThanOrEqual(44);
  expect(target.height, `${label} coarse-pointer height`).toBeGreaterThanOrEqual(44);
}

test.describe('coarse-pointer foundation controls', () => {
  test.use({ hasTouch: true });

  test('separates visible density from touch targets and keeps keyboard feedback', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/login');
    await setTheme(page, 'light');
    await expect(page.getByRole('heading', { name: 'StockPulse', exact: true })).toBeVisible();
    expect(await page.evaluate(() => matchMedia('(pointer: coarse)').matches)).toBe(true);

    const password = page.locator('#password');
    await expectVisibleHeights(password, inputHeights);
    expect(await password.locator('..').evaluate((element) => element.getBoundingClientRect().height))
      .toBeGreaterThanOrEqual(44);

    const passwordToggle = page.getByRole('button', { name: '显示内容' }).first();
    await expectVisibleHeights(passwordToggle, iconButtonHeights);
    await expectCoarseHitTarget(passwordToggle, 'password visibility action');

    const submit = page.getByRole('button', { name: /授权进入工作台|完成设置并登录/ });
    await expectVisibleHeights(submit, buttonHeights);
    await expectCoarseHitTarget(submit, 'login submit');

    await loginAsE2eAdmin(page);
    await page.goto('/backtest');
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
    await expect(page.getByRole('tooltip')).toHaveText(accessibleName || '');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('tooltip')).toHaveCount(0);

    await expectNoHorizontalOverflow(page, 'coarse-pointer backtest 390x844');
  });
});
