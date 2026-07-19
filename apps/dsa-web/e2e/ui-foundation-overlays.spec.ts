// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Locator, type Page } from '@playwright/test';
import { UI_LANGUAGE_STORAGE_KEY } from '../src/utils/uiLanguage';

async function openFixture(page: Page, width: number, height: number) {
  await page.setViewportSize({ width, height });
  await page.addInitScript((key) => localStorage.setItem(key, 'en'), UI_LANGUAGE_STORAGE_KEY);
  await page.goto('/e2e/overlay-contract-fixture.html');
  await expect(page.getByRole('heading', { name: 'Overlay contract fixture' })).toBeVisible();
}

async function expectFocusWithin(locator: Locator) {
  await expect.poll(() => locator.evaluate((element) => element.contains(document.activeElement))).toBe(true);
}

async function waitForAnimations(locator: Locator) {
  await locator.evaluate(async (element) => {
    await Promise.all(element.getAnimations().map((animation) => animation.finished));
  });
}

test.describe('semantic overlay foundation', () => {
  test('390x667 Filter Sheet keeps its footer reachable and closes nested layers one at a time', async ({ page }) => {
    await openFixture(page, 390, 667);
    const opener = page.getByTestId('open-filter-sheet');
    await opener.click();

    const sheet = page.getByRole('dialog', { name: 'More filters' });
    await expect(sheet).toBeVisible();
    await expectFocusWithin(sheet);
    await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('hidden');

    const footer = sheet.locator('[data-overlay-slot="footer"]');
    const footerBox = await footer.boundingBox();
    expect(footerBox).not.toBeNull();
    expect(footerBox!.y + footerBox!.height).toBeLessThanOrEqual(667);
    await expect(footer.getByRole('button', { name: 'Reset' })).toBeVisible();
    await expect(footer.getByRole('button', { name: 'View 12 results' })).toBeVisible();

    const popoverTrigger = sheet.getByTestId('open-nested-popover');
    await popoverTrigger.click();
    const menu = page.getByRole('menu', { name: 'Filter help actions' });
    await expect(menu).toBeVisible();
    await expect(menu).toHaveAttribute('data-dialog-popup', 'true');
    await page.keyboard.press('Escape');

    await expect(menu).toHaveCount(0);
    await expect(sheet).toBeVisible();
    await expect(popoverTrigger).toBeFocused();

    await sheet.getByRole('button', { name: 'View 12 results' }).focus();
    await page.keyboard.press('Tab');
    await expect(sheet.getByRole('button', { name: 'Close' })).toBeFocused();

    await popoverTrigger.click();
    await page.getByRole('menuitem', { name: 'Show status' }).click();
    const toast = page.getByRole('status');
    await expect(toast).toContainText('Overlay status ready');
    const toastRoot = page.locator('[data-overlay-root="toast"]').filter({ has: toast });
    await expect(toastRoot).not.toHaveAttribute('inert', '');
    await expect(toastRoot).not.toHaveAttribute('aria-hidden', 'true');
    expect(Number(await toastRoot.evaluate((element) => getComputedStyle(element).zIndex))).toBeGreaterThan(
      Number(await page.locator('[data-overlay-root="sheet"]').evaluate((element) => getComputedStyle(element).zIndex)),
    );

    await page.keyboard.press('Escape');
    await expect(sheet).toHaveCount(0);
    await expect(opener).toBeFocused();
    await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('');
  });

  test('320x700 navigation and detail drawers stay inside the viewport and restore their triggers', async ({ page }) => {
    await openFixture(page, 320, 700);

    const navigationOpener = page.getByTestId('open-navigation');
    await navigationOpener.click();
    const navigation = page.getByRole('dialog', { name: 'StockPulse navigation' });
    await expect(navigation).toHaveAttribute('data-drawer-variant', 'navigation');
    await waitForAnimations(navigation);
    let box = await navigation.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(320);
    await page.keyboard.press('Escape');
    await expect(navigationOpener).toBeFocused();

    const detailOpener = page.getByTestId('open-drawer');
    await detailOpener.click();
    const detail = page.getByRole('dialog', { name: 'Outer drawer' });
    await expect(detail).toHaveAttribute('data-drawer-variant', 'detail');
    await expect(detail).toHaveAttribute('data-drawer-size', 'default');
    await waitForAnimations(detail);
    box = await detail.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(320);
    expect(await detail.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.keyboard.press('Escape');
    await expect(detailOpener).toBeFocused();
  });

  test('desktop Modal keeps footer fixed while a nested Popover consumes the first Escape', async ({ page }) => {
    await openFixture(page, 1440, 900);
    const opener = page.getByTestId('open-modal');
    await opener.click();

    const modal = page.getByRole('dialog', { name: 'Outer modal' });
    await expect(modal.locator('[data-overlay-slot="header"]')).toBeVisible();
    await expect(modal.locator('[data-overlay-slot="body"]')).toBeVisible();
    await expect(modal.locator('[data-overlay-slot="footer"]')).toBeVisible();

    const popoverTrigger = modal.getByTestId('open-nested-popover');
    await popoverTrigger.click();
    await expect(page.getByRole('menu', { name: 'Modal help actions' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('menu', { name: 'Modal help actions' })).toHaveCount(0);
    await expect(modal).toBeVisible();
    await expect(popoverTrigger).toBeFocused();

    await page.keyboard.press('Escape');
    await expect(modal).toHaveCount(0);
    await expect(opener).toBeFocused();
  });
});
