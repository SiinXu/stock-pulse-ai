import { expect, test, type Locator, type Page } from '@playwright/test';

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

async function expectSidebarWidth(sidebar: Locator, width: number) {
  await expect.poll(async () => (
    Math.round((await sidebar.boundingBox())?.width ?? 0)
  ), {
    message: `sidebar should settle at ${width}px`,
  }).toBe(width);
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
      await expect(mobileHeader.getByRole('button')).toHaveCount(2);
      await expect(mobileHeader.getByText('StockPulse', { exact: true })).toBeVisible();
      const profile = mobileHeader.getByRole('button', { name: 'StockPulse' });
      await expect(profile).toBeVisible();
      expect((await profile.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
      await expect(opener).toHaveCount(1);
      await expect(opener).toBeVisible();
      expect((await opener.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
      await expect(page.locator('[data-shell-sidebar]')).toBeHidden();
      await expectNoDocumentOverflow(page);

      await opener.focus();
      await expect(page.getByRole('tooltip')).toHaveText('Open navigation');
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
    await expectSidebarWidth(sidebar, 80);
    const compactBrand = sidebar.locator('[data-shell-brand-mark]');
    await compactBrand.locator('..').hover();
    await expect(compactBrand).toHaveCSS('opacity', '0');
    const expand = sidebar.getByRole('button', { name: 'Expand sidebar' });
    await expect(expand).toHaveCSS('opacity', '1');
    await expand.click();
    await expect(sidebar).toHaveAttribute('data-shell-sidebar-mode', 'expanded');
    await expectSidebarWidth(sidebar, 240);
    expect(await page.evaluate(() => localStorage.getItem('dsa-sidebar-collapsed'))).toBe('0');
    await expectNoDocumentOverflow(page);

    for (const { width, height } of [
      { width: 1280, height: 820 },
      { width: 1440, height: 900 },
    ]) {
      await openFixture(page, width, height);
      await expect(sidebar).toHaveAttribute('data-shell-sidebar-mode', 'expanded');
      await expectSidebarWidth(sidebar, 240);
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
    await chatLink.focus();
    await chatLink.click({ modifiers: ['Control'] });
    await expect(drawer).toBeVisible();
    await expect(page).toHaveURL(/\/e2e\/application-shell-fixture\.html$/);
    await expect(chatLink).toBeFocused();
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

  test('keeps profile preferences directly reachable and restores trigger focus', async ({ page }) => {
    for (const { width, height } of [
      { width: 390, height: 844 },
      { width: 1440, height: 900 },
    ]) {
      await openFixture(page, width, height);
      const profileTrigger = page.getByRole('button', { name: 'StockPulse' }).filter({ visible: true });
      await expect(profileTrigger).toHaveCount(1);
      await expect(profileTrigger).toHaveAttribute('aria-haspopup', 'dialog');
      await profileTrigger.click();

      const profileDialog = page.getByRole('dialog', { name: 'StockPulse' });
      await expect(profileDialog).toBeVisible();
      const themeTrigger = profileDialog.getByRole('button', { name: 'Toggle theme' });
      await expect(themeTrigger).toBeFocused();
      expect((await themeTrigger.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
      await page.keyboard.press('Escape');
      await expect(profileDialog).toBeHidden();
      await expect(profileTrigger).toBeFocused();
    }
  });

  test('keeps the framed shell coherent and wide content reachable in both themes and reduced motion', async ({ page }) => {
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
        overflowX: style.overflowX,
      };
    })).toEqual(expect.objectContaining({
      borderTopWidth: '1px',
      overflowX: 'auto',
    }));
    await expect(main).not.toHaveCSS('border-radius', '0px');
    await expect(main).not.toHaveCSS('box-shadow', 'none');
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
    await expect(page.locator('[data-shell-brand-mark]')).toHaveCSS('transition-property', 'none');
    const scrollState = await main.evaluate((element) => {
      element.scrollLeft = 240;
      return {
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
        scrollLeft: element.scrollLeft,
      };
    });
    expect(scrollState.scrollWidth).toBeGreaterThan(scrollState.clientWidth);
    expect(scrollState.scrollLeft).toBeGreaterThan(0);
    await expectNoDocumentOverflow(page);
  });

  test('keeps compact navigation controls reachable in a short viewport', async ({ page }) => {
    await openFixture(page, 1024, 480);
    const sidebar = page.locator('[data-shell-sidebar]');
    const navigation = sidebar.getByRole('navigation', { name: 'Main navigation' });
    expect(await navigation.evaluate((element) => element.scrollHeight)).toBeGreaterThan(
      await navigation.evaluate((element) => element.clientHeight),
    );

    for (const control of [
      sidebar.getByRole('button', { name: 'Search' }),
      sidebar.getByRole('button', { name: 'StockPulse' }),
      sidebar.getByRole('button', { name: 'Log out' }),
    ]) {
      await expect(control).toBeVisible();
      expect((await control.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
    }

    const settings = navigation.getByRole('link', { name: 'Settings' });
    await settings.scrollIntoViewIfNeeded();
    const navigationBox = await navigation.boundingBox();
    const settingsBox = await settings.boundingBox();
    expect(settingsBox).not.toBeNull();
    expect(navigationBox).not.toBeNull();
    expect(settingsBox!.y).toBeGreaterThanOrEqual(navigationBox!.y - 1);
    expect(settingsBox!.y + settingsBox!.height).toBeLessThanOrEqual(
      navigationBox!.y + navigationBox!.height + 1,
    );

    const search = sidebar.getByRole('button', { name: 'Search' });
    await search.focus();
    await expect(page.getByRole('tooltip')).toHaveText('Search');
    const home = navigation.getByRole('link', { name: 'Home' });
    await home.focus();
    await expect(page.getByRole('tooltip')).toHaveText('Home');
    await expectNoDocumentOverflow(page);
  });
});
