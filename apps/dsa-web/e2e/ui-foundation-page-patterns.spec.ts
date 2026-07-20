// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { expect, test, type Page } from '@playwright/test';

const VIEWPORTS = [
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

async function openFixture(page: Page, width: number, height: number) {
  await page.setViewportSize({ width, height });
  await page.goto('/e2e/page-pattern-fixture.html');
  await expect(page.getByRole('heading', { level: 1, name: 'Portfolio overview' })).toBeVisible();
}

async function expectNoDocumentOverflow(page: Page, label: string) {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content, `${label}: ${dimensions.content}px content in ${dimensions.viewport}px viewport`)
    .toBeLessThanOrEqual(dimensions.viewport + 1);
}

test.describe('shared page and Router Patterns', () => {
  test('keeps landmark, heading, navigation, toolbar, summary, and Tabs semantics distinct', async ({ page }) => {
    await openFixture(page, 1024, 768);
    await expect(page.locator('main')).toHaveCount(1);
    await expect(page.locator('h1')).toHaveCount(1);
    await expect(page.locator('[data-pattern="app-page"]')).toHaveJSProperty('tagName', 'DIV');
    await expect(page.getByRole('toolbar', { name: 'Workspace commands' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Workspace views' }).getByRole('tab')).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Overview' })).toHaveAttribute('aria-current', 'page');
    await expect(page.getByLabel('Analysis summary')).toHaveJSProperty('tagName', 'DL');

    const summaryTab = page.getByRole('tab', { name: 'Summary' });
    await summaryTab.focus();
    await page.keyboard.press('ArrowRight');
    await expect(page.getByRole('tab', { name: 'Risk and freshness' })).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('tabpanel')).toContainText('Risk is elevated');
  });

  test('preserves the desktop opener through repeated Back and Forward navigation', async ({ page }) => {
    await openFixture(page, 1024, 768);
    await page.getByRole('link', { name: 'Detailed evidence' }).click();
    await expect(page).toHaveURL(/\/e2e\/page-pattern-details-fixture\.html$/);
    const detailsHeading = page.getByRole('heading', {
      level: 1,
      name: 'Detailed evidence and risk review for the current portfolio',
    });
    await expect(detailsHeading).toBeFocused();

    await page.goBack();
    await expect(page).toHaveURL(/\/e2e\/page-pattern-fixture\.html$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Portfolio overview' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Detailed evidence' })).toBeFocused();

    await page.goForward();
    await expect(page).toHaveURL(/\/e2e\/page-pattern-details-fixture\.html$/);
    await expect(detailsHeading).toBeFocused();

    await page.goBack();
    await expect(page).toHaveURL(/\/e2e\/page-pattern-fixture\.html$/);
    await expect(page.getByRole('link', { name: 'Detailed evidence' })).toBeFocused();
  });

  test('restores the details-page Back trigger on Forward', async ({ page }) => {
    await openFixture(page, 1024, 768);
    await page.getByRole('link', { name: 'Detailed evidence' }).click();
    const backButton = page.getByRole('button', { name: 'Back' });
    await backButton.click();
    await expect(page.getByRole('link', { name: 'Detailed evidence' })).toBeFocused();

    await page.goForward();
    await expect(page).toHaveURL(/\/e2e\/page-pattern-details-fixture\.html$/);
    await expect(backButton).toBeFocused();
  });

  test('treats reload as direct entry and never persists route-focus metadata', async ({ page }) => {
    await openFixture(page, 1024, 768);
    const storageBeforeNavigation = await page.evaluate(() => ({
      localStorage: JSON.stringify({ ...window.localStorage }),
      sessionStorage: JSON.stringify({ ...window.sessionStorage }),
    }));
    await page.getByRole('link', { name: 'Detailed evidence' }).click();
    const heading = page.getByRole('heading', {
      level: 1,
      name: 'Detailed evidence and risk review for the current portfolio',
    });
    await expect(heading).toBeFocused();

    const persistedBeforeReload = await page.evaluate(() => ({
      url: window.location.href,
      historyState: JSON.stringify(window.history.state),
      localStorage: JSON.stringify({ ...window.localStorage }),
      sessionStorage: JSON.stringify({ ...window.sessionStorage }),
    }));
    expect(persistedBeforeReload.localStorage).toBe(storageBeforeNavigation.localStorage);
    expect(persistedBeforeReload.sessionStorage).toBe(storageBeforeNavigation.sessionStorage);
    for (const value of Object.values(persistedBeforeReload)) {
      expect(value).not.toContain('fixture-workspace-navigation:details');
      expect(value).not.toContain('route-focus');
    }

    await page.reload();
    await expect(heading).toBeVisible();
    await expect(heading).not.toBeFocused();
    const persistedAfterReload = await page.evaluate(() => ({
      url: window.location.href,
      historyState: JSON.stringify(window.history.state),
      localStorage: JSON.stringify({ ...window.localStorage }),
      sessionStorage: JSON.stringify({ ...window.sessionStorage }),
    }));
    for (const value of Object.values(persistedAfterReload)) {
      expect(value).not.toContain('fixture-workspace-navigation:details');
      expect(value).not.toContain('route-focus');
    }
  });

  test('uses native compact navigation and restores its focus on Back', async ({ page }) => {
    await openFixture(page, 390, 667);
    const compactNavigation = page.getByRole('combobox', { name: 'Workspace views' });
    await compactNavigation.selectOption('details');
    await expect(page).toHaveURL(/\/e2e\/page-pattern-details-fixture\.html$/);
    await expect(page.getByRole('heading', {
      level: 1,
      name: 'Detailed evidence and risk review for the current portfolio',
    })).toBeFocused();

    await page.getByRole('button', { name: 'Back' }).click();
    await expect(page).toHaveURL(/\/e2e\/page-pattern-fixture\.html$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Portfolio overview' })).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Workspace views' })).toBeFocused();
  });

  test('falls back to the H1 when the original opener becomes hidden at another breakpoint', async ({ page }) => {
    await openFixture(page, 1024, 768);
    await page.getByRole('link', { name: 'Detailed evidence' }).click();
    await expect(page.getByRole('heading', {
      level: 1,
      name: 'Detailed evidence and risk review for the current portfolio',
    })).toBeFocused();

    await page.setViewportSize({ width: 390, height: 667 });
    await page.getByRole('button', { name: 'Back' }).click();
    const overviewHeading = page.getByRole('heading', { level: 1, name: 'Portfolio overview' });
    await expect(overviewHeading).toBeFocused();
    await expect(page.getByRole('link', { name: 'Detailed evidence' })).toBeHidden();
  });

  test('retains control focus when Router query state changes on the same page', async ({ page }) => {
    await openFixture(page, 1024, 768);
    const queryControl = page.getByRole('button', { name: 'Update URL state' });
    await queryControl.focus();
    await queryControl.click();
    await expect(page).toHaveURL(/\/e2e\/page-pattern-fixture\.html\?view=compact$/);
    await page.evaluate(() => new Promise<void>((resolve) => {
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve()));
    }));
    await expect(queryControl).toBeFocused();
    await expect(page.getByRole('heading', { level: 1, name: 'Portfolio overview' })).not.toBeFocused();
  });

  test('contains the rail and long content across all fixed viewports', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const viewport of VIEWPORTS) {
      await openFixture(page, viewport.width, viewport.height);
      await expectNoDocumentOverflow(page, `${viewport.width}x${viewport.height}`);
      const railContent = page.getByTestId('rail-content');
      const toggle = page.getByRole('button', { name: 'Show workspace context' });
      if (viewport.width >= 1280) {
        await expect(toggle).toBeHidden();
        await expect(railContent).toBeVisible();
      } else if (viewport.width >= 768 && viewport.width < 1024) {
        await expect(toggle).toBeVisible();
        await expect(toggle).toHaveAttribute('aria-haspopup', 'dialog');
        await expect(railContent).toHaveCount(0);
        await toggle.focus();
        await toggle.click();
        const drawer = page.getByRole('dialog', { name: 'Workspace context' });
        await expect(drawer.getByTestId('rail-content')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(drawer).toBeHidden();
        await expect(toggle).toBeFocused();
      } else {
        await expect(toggle).toBeVisible();
        await expect(railContent).toBeHidden();
        await toggle.click();
        await expect(railContent).toBeVisible();
      }
    }
  });

  test('closes an open tablet business rail when the presentation changes', async ({ page }) => {
    await openFixture(page, 900, 800);
    const toggle = page.getByRole('button', { name: 'Show workspace context' });
    await toggle.click();
    await expect(page.getByRole('dialog', { name: 'Workspace context' })).toBeVisible();

    await page.setViewportSize({ width: 1024, height: 768 });

    await expect(page.getByRole('dialog', { name: 'Workspace context' })).toBeHidden();
    await expect(toggle).toBeFocused();
    await expect(page.getByTestId('rail-content')).toBeHidden();
  });

  test('preserves both semantic theme states without horizontal overflow', async ({ page }) => {
    await openFixture(page, 320, 700);
    await page.evaluate(() => localStorage.setItem('theme', 'light'));
    await page.reload();
    await expect(page.locator('html')).toHaveClass(/(?:^|\s)light(?:\s|$)/);
    await expectNoDocumentOverflow(page, 'light 320x700');

    await page.evaluate(() => localStorage.setItem('theme', 'dark'));
    await page.reload();
    await expect(page.locator('html')).toHaveClass(/(?:^|\s)dark(?:\s|$)/);
    await expectNoDocumentOverflow(page, 'dark 320x700');
  });
});
