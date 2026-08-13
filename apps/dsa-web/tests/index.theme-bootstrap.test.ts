// @vitest-environment node

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('index.html theme bootstrap', () => {
  it('preloads dark mode before React mounts and respects stored theme values', () => {
    const indexHtml = readFileSync(resolve(__dirname, '..', 'index.html'), 'utf8');

    expect(indexHtml).toContain("const storageKey = 'theme'");
    expect(indexHtml).toContain("const theme = storedTheme === 'light' || storedTheme === 'dark' ? storedTheme : 'dark';");
    expect(indexHtml).toContain("root.classList.remove('light', 'dark');");
    expect(indexHtml).toContain('root.classList.add(theme);');
    expect(indexHtml).toContain('root.style.colorScheme = theme;');
  });

  it('bootstraps theme pack and CN-default price direction before paint', () => {
    const indexHtml = readFileSync(resolve(__dirname, '..', 'index.html'), 'utf8');

    expect(indexHtml).toContain("const packKey = 'theme-pack'");
    expect(indexHtml).toContain("const priceDirectionKey = 'price-direction'");
    expect(indexHtml).toContain("root.setAttribute('data-theme-pack', pack)");
    expect(indexHtml).toContain("root.setAttribute('data-price-direction', priceDirection)");
    expect(indexHtml).toContain("storedPriceDirection === 'us' || storedPriceDirection === 'cn'");
  });
});
