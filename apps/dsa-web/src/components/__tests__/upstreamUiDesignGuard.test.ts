/// <reference types="vite/client" />
import { describe, expect, it } from 'vitest';
// Load the component sources as raw strings via Vite's `?raw` loader (no Node
// built-ins, so the production `tsc -b` build type-checks this cleanly).
import homeStockWorkspaceSource from '../watchlist/HomeStockWorkspace.tsx?raw';
import marketStructureCardSource from '../report/MarketStructureCard.tsx?raw';

// Regression guard for the upstream-merge integration: the upstream home
// watchlist workspace and market-structure card must be adapted to the
// StockPulse design system (apps/dsa-web/DESIGN_GUIDE.md) and must NOT reintroduce
// the old upstream visuals — no cyan/purple glow, no hardcoded hex in components
// (hex only belongs in src/index.css :root/.dark), no colored-glow shadows.
const UPSTREAM_UI_SOURCES: Array<[string, string]> = [
  ['watchlist/HomeStockWorkspace.tsx', homeStockWorkspaceSource],
  ['report/MarketStructureCard.tsx', marketStructureCardSource],
];

describe('upstream UI adapts to the StockPulse design system', () => {
  for (const [name, content] of UPSTREAM_UI_SOURCES) {
    it(`${name} uses design tokens (no cyan/purple/glow/hardcoded hex)`, () => {
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
