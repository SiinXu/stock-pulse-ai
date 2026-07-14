import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

// Regression guard for the upstream-merge integration: the upstream home
// watchlist workspace and market-structure card must be adapted to the
// StockPulse design system (apps/dsa-web/DESIGN_GUIDE.md) and must NOT reintroduce
// the old upstream visuals — no cyan/purple glow, no hardcoded hex in components
// (hex only belongs in src/index.css :root/.dark), no colored-glow shadows.
const here = dirname(fileURLToPath(import.meta.url));
// here = apps/dsa-web/src/components/__tests__ ; components dir is its parent.
const componentsDir = resolve(here, '..');

const UPSTREAM_UI_FILES = [
  'watchlist/HomeStockWorkspace.tsx',
  'report/MarketStructureCard.tsx',
];

describe('upstream UI adapts to the StockPulse design system', () => {
  for (const rel of UPSTREAM_UI_FILES) {
    it(`${rel} uses design tokens (no cyan/purple/glow/hardcoded hex)`, () => {
      const content = readFileSync(resolve(componentsDir, rel), 'utf-8');
      // No legacy cyan/purple color utility classes.
      expect(content).not.toMatch(/\b(?:text|bg|border|ring)-cyan\b/);
      expect(content).not.toMatch(/\b(?:text|bg|border|ring)-purple\b/);
      // No colored glow / pulse-glow effects.
      expect(content).not.toMatch(/pulse-glow|glow-cyan|glow-purple|shadow-glow/);
      // No hardcoded hex colours inside a component (tokens only).
      expect(content).not.toMatch(/#[0-9a-fA-F]{3,6}\b/);
    });
  }
});
