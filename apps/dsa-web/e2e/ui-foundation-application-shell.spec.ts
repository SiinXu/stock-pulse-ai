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

  test('keeps per-entry mobile focus through three routes and repeated Back and Forward', async ({ page }) => {
    await openFixture(page, 390, 844);
    const opener = page.getByRole('button', { name: 'Open navigation' });
    await opener.click();
    const drawer = page.getByRole('dialog', { name: 'Navigation' });
    const chatLink = drawer.getByRole('link', { name: 'Agent' });
    await expect(chatLink).toHaveAttribute('data-route-focus-key', 'shell-nav-mobile:agent');
    await expect(chatLink).toHaveAttribute('data-route-focus-return-key', 'shell:mobile-navigation');
    await chatLink.focus();
    await chatLink.click({ modifiers: ['Control'] });
    await expect(drawer).toBeVisible();
    await expect(page).toHaveURL(/\/e2e\/application-shell-fixture\.html$/);
    await expect(chatLink).toBeFocused();
    await chatLink.click();

    await expect(drawer).toBeHidden();
    await expect(page).toHaveURL(/\/chat$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Route /chat' })).toBeFocused();
    await expect(opener).toHaveAttribute('data-route-focus-key', 'shell:mobile-navigation');

    await opener.click();
    await drawer.getByRole('link', { name: 'Portfolio' }).click();
    await expect(drawer).toBeHidden();
    await expect(page).toHaveURL(/\/portfolio$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Route /portfolio' })).toBeFocused();

    await page.goBack();
    await expect(page).toHaveURL(/\/chat$/);
    await expect(opener).toBeFocused();

    await page.goBack();
    await expect(page).toHaveURL(/\/e2e\/application-shell-fixture\.html$/);
    await expect(opener).toBeFocused();

    await page.goForward();
    await expect(page).toHaveURL(/\/chat$/);
    await expect(opener).toBeFocused();

    await page.goForward();
    await expect(page).toHaveURL(/\/portfolio$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Route /portfolio' })).toBeFocused();

    await page.goBack();
    await expect(page).toHaveURL(/\/chat$/);
    await expect(opener).toBeFocused();
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

  test('closes Profile at the desktop breakpoint and focuses the visible counterpart', async ({ page }) => {
    await openFixture(page, 390, 844);
    const mobileProfile = page.locator('[data-shell-profile-trigger="mobile"]');
    await mobileProfile.click();
    const profileDialog = page.getByRole('dialog', { name: 'StockPulse' });
    await expect(profileDialog).toBeVisible();
    await expect(profileDialog.getByRole('button', { name: 'Toggle theme' })).toBeFocused();

    await page.setViewportSize({ width: 1024, height: 768 });
    const desktopProfile = page.locator('[data-shell-profile-trigger="desktop"]');
    await expect(profileDialog).toBeHidden();
    await expect(desktopProfile).toBeVisible();
    await expect(desktopProfile).toBeFocused();

    await desktopProfile.click();
    await expect(profileDialog).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(profileDialog).toBeHidden();
    await expect(mobileProfile).toBeVisible();
    await expect(mobileProfile).toBeFocused();
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

  test('keeps expanded and mobile route rows at 44px in a short viewport', async ({ page }) => {
    await openFixture(page, 1024, 480);
    const sidebar = page.locator('[data-shell-sidebar]');
    const compactSearch = sidebar.getByRole('button', { name: 'Search', exact: true });
    await compactSearch.focus();
    await expect(page.getByRole('tooltip')).toHaveText('Search');
    const compactHome = sidebar.getByRole('link', { name: 'Home' });
    await compactHome.focus();
    await compactHome.press('ArrowRight');
    const homeMenu = page.getByRole('menu', { name: 'Home' });
    await expect(homeMenu).toBeVisible();
    await expect(homeMenu.getByRole('menuitem', { name: 'Signal Center' })).toBeVisible();
    await expect(homeMenu.getByRole('menuitem')).toHaveCount(1);
    await page.keyboard.press('Escape');
    await expect(homeMenu).toBeHidden();
    await expect(compactHome).toBeFocused();

    const compactResearch = sidebar.getByRole('link', { name: 'Research' });
    await compactResearch.hover();
    const researchMenu = page.getByRole('menu', { name: 'Research' });
    await expect(researchMenu.getByRole('menuitem', { name: 'Market review' })).toBeVisible();
    await expect(researchMenu.getByRole('menuitem', { name: 'Discover' })).toBeVisible();
    await expect(researchMenu.getByRole('menuitem', { name: 'Backtest' })).toBeVisible();
    await researchMenu.getByRole('menuitem', { name: 'Discover' }).click();
    await expect(page).toHaveURL(/\/research\/discover$/);
    await expect(compactResearch).toHaveAttribute('aria-current', 'page');
    const compactNavigation = sidebar.getByRole('navigation', { name: 'Main navigation' });
    const compactRoutes = await compactNavigation.getByRole('link').all();
    expect(compactRoutes).toHaveLength(5);
    for (const route of compactRoutes) {
      expect((await route.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
    }
    await sidebar.getByRole('button', { name: 'Expand sidebar' }).click();
    await expectSidebarWidth(sidebar, 240);
    const navigation = sidebar.getByRole('navigation', { name: 'Main navigation' });
    const researchToggle = navigation.getByRole('button', { name: 'Research' });
    const researchParent = navigation.getByRole('link', { name: 'Research' });
    const discoverChild = navigation.getByRole('link', { name: 'Discover' });
    await expect(researchToggle).toHaveAttribute('aria-expanded', 'true');
    await expect(researchParent).not.toHaveAttribute('aria-current');
    await expect(discoverChild).toHaveAttribute('aria-current', 'page');
    await researchToggle.click();
    await expect(researchToggle).toHaveAttribute('aria-expanded', 'false');
    await expect(navigation.getByRole('link', { name: 'Discover' })).toBeHidden();
    await expect(researchParent).toHaveAttribute('aria-current', 'page');
    await researchToggle.click();
    await expect(researchToggle).toHaveAttribute('aria-expanded', 'true');
    await expect(navigation.getByRole('link', { name: 'Discover' })).toBeVisible();
    await expect(researchParent).not.toHaveAttribute('aria-current');
    await expect(discoverChild).toHaveAttribute('aria-current', 'page');
    expect(await navigation.evaluate((element) => element.scrollHeight)).toBeGreaterThan(
      await navigation.evaluate((element) => element.clientHeight),
    );
    for (const route of await navigation.getByRole('link').all()) {
      expect((await route.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
    }

    for (const control of [
      sidebar.getByRole('button', { name: 'Search', exact: true }),
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

    const search = sidebar.getByRole('button', { name: 'Search', exact: true });
    await search.focus();
    await expect(search).toBeFocused();
    await expectNoDocumentOverflow(page);

    await page.setViewportSize({ width: 390, height: 480 });
    await page.getByRole('button', { name: 'Open navigation' }).click();
    const drawer = page.getByRole('dialog', { name: 'Navigation' });
    const mobileNavigation = drawer.getByRole('navigation', { name: 'Main navigation' });
    const mobileResearchToggle = mobileNavigation.getByRole('button', { name: 'Research' });
    await expect(mobileResearchToggle).toHaveAttribute('aria-expanded', 'true');
    await mobileResearchToggle.click();
    await expect(mobileResearchToggle).toHaveAttribute('aria-expanded', 'false');
    await expect(mobileNavigation.getByRole('link', { name: 'Discover' })).toBeHidden();
    await mobileResearchToggle.click();
    await expect(mobileResearchToggle).toHaveAttribute('aria-expanded', 'true');
    await expect(mobileNavigation.getByRole('link', { name: 'Discover' })).toBeVisible();
    expect(await mobileNavigation.evaluate((element) => element.scrollHeight)).toBeGreaterThan(
      await mobileNavigation.evaluate((element) => element.clientHeight),
    );
    for (const route of await mobileNavigation.getByRole('link').all()) {
      expect((await route.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
    }
    const mobileSettings = mobileNavigation.getByRole('link', { name: 'Settings' });
    await mobileSettings.scrollIntoViewIfNeeded();
    await expect(mobileSettings).toBeVisible();
    await expectNoDocumentOverflow(page);
  });
});

test.describe('application shell touch panning', () => {
  test.use({ hasTouch: true });

  test('moves the mobile main scroll container with a horizontal touch gesture', async ({ page }) => {
    await openFixture(page, 390, 844);
    const main = page.locator('[data-shell-main]');
    await expect(main).toHaveCSS('touch-action', 'auto');
    expect(await main.evaluate((element) => element.scrollWidth)).toBeGreaterThan(
      await main.evaluate((element) => element.clientWidth),
    );
    await main.evaluate((element) => { element.scrollLeft = 0; });

    const box = await main.boundingBox();
    expect(box).not.toBeNull();
    const startX = box!.x + box!.width - 36;
    const endX = box!.x + 44;
    const y = box!.y + Math.min(260, box!.height / 2);
    const session = await page.context().newCDPSession(page);
    await session.send('Input.dispatchTouchEvent', {
      type: 'touchStart',
      touchPoints: [{ x: startX, y }],
    });
    for (let step = 1; step <= 6; step += 1) {
      await session.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [{ x: startX + ((endX - startX) * step) / 6, y }],
      });
    }
    await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await session.detach();

    await expect.poll(() => main.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
    await expectNoDocumentOverflow(page);
  });
});
