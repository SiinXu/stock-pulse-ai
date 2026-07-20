import { expect, test, type Page } from '@playwright/test';

const FIXTURE_PATH = '/e2e/application-shell-fixture.html';

async function openFixture(page: Page, width: number, height = 800) {
  await page.setViewportSize({ width, height });
  await page.goto(FIXTURE_PATH);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
}

async function expectNoDocumentOverflow(page: Page) {
  expect(await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))).toEqual(expect.objectContaining({
    scrollWidth: await page.evaluate(() => document.documentElement.clientWidth),
  }));
}

test.describe('application shell foundation', () => {
  test('uses one Drawer opener below 1024 and restores it on Escape and close', async ({ page }) => {
    const mobileViewports = [
      { width: 320, height: 700 },
      { width: 390, height: 667 },
      { width: 390, height: 844 },
      { width: 767, height: 900 },
      { width: 768, height: 900 },
      { width: 900, height: 800 },
    ];

    for (const { width, height } of mobileViewports) {
      await openFixture(page, width, height);
      const mobileHeader = page.locator('[data-shell-mobile-header]');
      const opener = page.getByRole('button', { name: 'Open navigation' });
      await expect(mobileHeader.getByRole('button')).toHaveCount(1);
      await expect(mobileHeader.getByText('StockPulse', { exact: true })).toBeVisible();
      await expect(opener).toHaveCount(1);
      await expect(opener).toBeVisible();
      await expect(page.locator('[data-shell-sidebar]')).toBeHidden();
      await expectNoDocumentOverflow(page);

      await opener.focus();
      await opener.click();
      const drawer = page.getByRole('dialog', { name: 'Navigation' });
      await expect(drawer).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(drawer).toBeHidden();
      await expect(opener).toBeFocused();

      await opener.click();
      await drawer.getByRole('button', { name: 'Close drawer' }).click();
      await expect(drawer).toBeHidden();
      await expect(opener).toBeFocused();
    }
  });

  test('uses a compact rail at 1024 and an expanded brand at wider desktop sizes', async ({ page }) => {
    await openFixture(page, 1024, 768);
    const sidebar = page.locator('[data-shell-sidebar]');
    await expect(sidebar).toBeVisible();
    await expect(sidebar).toHaveAttribute('data-shell-sidebar-mode', 'compact');
    await expect(page.getByRole('button', { name: 'Open navigation' })).toBeHidden();
    expect(Math.round((await sidebar.boundingBox())?.width ?? 0)).toBe(76);
    const compactBrand = sidebar.locator('[data-shell-brand-mark]');
    await compactBrand.locator('..').hover();
    await expect(compactBrand).toHaveCSS('opacity', '1');
    await expectNoDocumentOverflow(page);

    for (const { width, height } of [
      { width: 1280, height: 820 },
      { width: 1440, height: 900 },
    ]) {
      await openFixture(page, width, height);
      await expect(sidebar).toHaveAttribute('data-shell-sidebar-mode', 'expanded');
      await expect(sidebar.getByText('StockPulse', { exact: true }).first()).toBeVisible();
      await expectNoDocumentOverflow(page);
    }
  });

  test('keeps content width monotonic across the 768, 900, and 1024 breakpoints', async ({ page }) => {
    const widths: number[] = [];
    for (const { width, height } of [
      { width: 768, height: 900 },
      { width: 900, height: 800 },
      { width: 1024, height: 768 },
    ]) {
      await openFixture(page, width, height);
      widths.push(Math.round((await page.locator('[data-shell-main]').boundingBox())?.width ?? 0));
      await expectNoDocumentOverflow(page);
    }

    expect(widths[0]).toBeLessThan(widths[1]);
    expect(widths[1]).toBeLessThan(widths[2]);
  });

  test('moves focus from an open mobile Drawer to the active desktop route at 1024', async ({ page }) => {
    await openFixture(page, 900, 800);
    await page.getByRole('button', { name: 'Open navigation' }).click();
    const drawer = page.getByRole('dialog', { name: 'Navigation' });
    await expect(drawer).toBeVisible();

    await page.setViewportSize({ width: 1024, height: 768 });

    await expect(drawer).toBeHidden();
    await expect(page.locator('[data-shell-sidebar]')).toBeFocused();

    await page.setViewportSize({ width: 900, height: 800 });
    const heading = page.getByRole('heading', { level: 1 });
    await heading.focus();
    await page.setViewportSize({ width: 1024, height: 768 });
    await expect(heading).toBeFocused();
  });

  test('delegates route focus to the H1 and restores the persistent mobile opener on Back', async ({ page }) => {
    await openFixture(page, 390, 844);
    await page.getByRole('button', { name: 'Open navigation' }).click();
    const drawer = page.getByRole('dialog', { name: 'Navigation' });
    const chatLink = drawer.getByRole('link', { name: 'Ask' });
    await expect(chatLink).toHaveAttribute('data-route-focus-key', 'shell-nav-mobile:chat');
    await chatLink.click();

    await expect(drawer).toBeHidden();
    await expect(page).toHaveURL(/\/chat$/);
    const heading = page.getByRole('heading', { level: 1, name: 'Route /chat' });
    await expect(heading).toBeFocused();
    await expect(page.getByRole('button', { name: 'Open navigation' })).toHaveAttribute(
      'data-route-focus-key',
      'shell-nav-mobile:chat',
    );

    await page.goBack();
    await expect(page).toHaveURL(/\/e2e\/application-shell-fixture\.html$/);
    await expect(page.getByRole('button', { name: 'Open navigation' })).toBeFocused();
  });

  test('uses dialog semantics for profile preferences and restores trigger focus', async ({ page }) => {
    await openFixture(page, 1440, 900);
    const profileTrigger = page.getByRole('button', { name: 'StockPulse' });
    await expect(profileTrigger).toHaveAttribute('aria-haspopup', 'dialog');
    await profileTrigger.click();

    const profileDialog = page.getByRole('dialog', { name: 'StockPulse' });
    await expect(profileDialog).toBeVisible();
    const themeTrigger = profileDialog.getByRole('button', { name: 'Toggle theme' });
    await expect(themeTrigger).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(profileDialog).toBeHidden();
    await expect(profileTrigger).toBeFocused();
  });

  test('keeps the full-bleed shell coherent in light, dark, and reduced motion', async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('theme', 'light'));
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await openFixture(page, 1024, 768);
    const main = page.locator('[data-shell-main]');
    await expect(main).toBeVisible();
    expect(await main.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        borderRadius: style.borderRadius,
        borderTopWidth: style.borderTopWidth,
        boxShadow: style.boxShadow,
      };
    })).toEqual({
      borderRadius: '0px',
      borderTopWidth: '0px',
      boxShadow: 'none',
    });
    await expect(page.locator('html')).toHaveClass(/light/);

    const lightBackground = await main.evaluate((element) => getComputedStyle(element).backgroundColor);
    await page.getByRole('button', { name: 'StockPulse' }).click();
    await page.getByRole('dialog', { name: 'StockPulse' })
      .getByRole('button', { name: 'Toggle theme' })
      .click();
    await page.getByRole('menuitemradio', { name: 'Dark' }).click();
    await expect(page.locator('html')).toHaveClass(/dark/);

    await expect.poll(
      () => main.evaluate((element) => getComputedStyle(element).backgroundColor),
    ).not.toBe(lightBackground);
    expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
    await expect(page.locator('[data-shell-sidebar]')).toHaveCSS('transition-property', 'none');
    await expectNoDocumentOverflow(page);
  });
});
