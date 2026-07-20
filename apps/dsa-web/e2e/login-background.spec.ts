import { expect, test } from '@playwright/test';

const themes = ['light', 'dark'] as const;
const viewports = [
  { label: 'mobile', width: 390, height: 844 },
  { label: 'desktop', width: 1440, height: 900 },
] as const;

test.describe('login background treatment', () => {
  for (const theme of themes) {
    for (const viewport of viewports) {
      test(`${theme} ${viewport.label} keeps the approved decoration and responsive fit`, async ({ page }) => {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await page.addInitScript((nextTheme) => {
          window.localStorage.setItem('theme', nextTheme);
        }, theme);
        await page.goto('/login');

        const pageRoot = page.getByTestId('login-page');
        const grid = page.getByTestId('login-grid-background');
        const accents = page.getByTestId('login-accent-background');
        await expect(pageRoot).toBeVisible();
        await expect(page.locator('html')).toHaveClass(new RegExp(`(^|\\s)${theme}(\\s|$)`));

        const treatment = await page.evaluate(() => {
          const root = document.querySelector<HTMLElement>('[data-testid="login-page"]');
          const gridLayer = document.querySelector<HTMLElement>('[data-testid="login-grid-background"]');
          const accentLayer = document.querySelector<HTMLElement>('[data-testid="login-accent-background"]');
          if (!root || !gridLayer || !accentLayer) {
            throw new Error('Login background layers were not rendered');
          }
          const headings = Array.from(root.querySelectorAll<HTMLElement>('h1, h2'));

          const probe = document.createElement('div');
          probe.style.backgroundColor = 'var(--login-bg-main)';
          document.body.appendChild(probe);
          const expectedRootBackground = getComputedStyle(probe).backgroundColor;
          probe.remove();

          const rootStyle = getComputedStyle(root);
          const gridStyle = getComputedStyle(gridLayer);
          const accentStyle = getComputedStyle(accentLayer);
          const rootRect = root.getBoundingClientRect();
          return {
            accentBackgroundImage: accentStyle.backgroundImage,
            documentWidth: document.documentElement.scrollWidth,
            expectedRootBackground,
            gridBackgroundImage: gridStyle.backgroundImage,
            gridBackgroundSize: gridStyle.backgroundSize,
            gridMaskImage: gridStyle.maskImage,
            headingUsesTightTracking: headings.map((heading) => heading.classList.contains('tracking-tight')),
            rootBackground: rootStyle.backgroundColor,
            rootHeight: rootRect.height,
            viewportHeight: window.innerHeight,
            viewportWidth: window.innerWidth,
          };
        });

        expect((treatment.gridBackgroundImage.match(/linear-gradient/g) ?? [])).toHaveLength(2);
        expect(treatment.gridBackgroundSize).toBe('24px 24px, 24px 24px');
        expect(treatment.gridMaskImage).toContain('radial-gradient');
        expect((treatment.accentBackgroundImage.match(/radial-gradient/g) ?? [])).toHaveLength(2);
        expect(treatment.rootBackground).toBe(treatment.expectedRootBackground);
        expect(treatment.headingUsesTightTracking).toEqual([false, false]);
        expect(treatment.documentWidth).toBe(treatment.viewportWidth);
        expect(treatment.rootHeight).toBeGreaterThanOrEqual(treatment.viewportHeight);
        await expect(grid).toHaveAttribute('aria-hidden', 'true');
        await expect(accents).toHaveAttribute('aria-hidden', 'true');
      });
    }
  }
});
