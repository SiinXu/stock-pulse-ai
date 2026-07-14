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
// (hex only belongs in src/index.css :root/.dark), no colored-glow shadows,
// no magic pixel font sizes, and buttons must stay pill shaped (rounded-full).
const UPSTREAM_UI_SOURCES: Array<[string, string]> = [
  ['watchlist/HomeStockWorkspace.tsx', homeStockWorkspaceSource],
  ['report/MarketStructureCard.tsx', marketStructureCardSource],
];

// Matches an opening `<button ...>` / `<Button ...>` tag. `(?:=>|[^>])*?`
// tolerates arrow functions inside inline handlers (`onClick={() => ...}`)
// while still stopping at the real end of the opening tag, so the assertion
// only sees button attributes and never leaks into card/container markup.
const BUTTON_OPENING_TAG_PATTERN = /<(?:button|Button)\b(?:=>|[^>])*?>/g;

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

    it(`${name} avoids magic pixel font sizes (use the Tailwind type scale)`, () => {
      // e.g. text-[11px] / text-[10px] — use text-xs/text-sm/... instead.
      expect(content).not.toMatch(/text-\[\d+px\]/);
    });

    it(`${name} keeps buttons pill shaped (no rounded-lg/rounded-md on buttons)`, () => {
      const buttonOpeningTags = content.match(BUTTON_OPENING_TAG_PATTERN) ?? [];
      for (const tag of buttonOpeningTags) {
        expect(tag).not.toMatch(/\brounded-(?:lg|md)\b/);
      }
    });
  }

  it('button shape guard actually sees the workspace buttons', () => {
    // Sanity check: HomeStockWorkspace renders native <button> tabs and
    // <Button> actions; if the extraction regex ever stops matching, the
    // shape assertions above would silently pass on an empty list.
    const tags = homeStockWorkspaceSource.match(BUTTON_OPENING_TAG_PATTERN) ?? [];
    expect(tags.length).toBeGreaterThan(0);
  });
});
