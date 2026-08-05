// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  formatMarketReviewRegionLabels,
  formatMarketReviewRegionSelection,
  parseMarketReviewRegionTokens,
  serializeMarketReviewRegions,
} from '../marketReviewRegion';

const zhLabels = {
  cn: 'A 股',
  hk: '港股',
  us: '美股',
  jp: '日股',
  kr: '韩股',
} as const;

describe('marketReviewRegion helpers', () => {
  it('serializes full selection as both and partial as ordered tokens', () => {
    expect(serializeMarketReviewRegions(['kr', 'jp'])).toBe('jp,kr');
    expect(serializeMarketReviewRegions(['cn', 'hk', 'us', 'jp', 'kr'])).toBe('both');
  });

  it('parses backend tokens, expands both, and drops unknowns', () => {
    expect(parseMarketReviewRegionTokens('cn,hk,us')).toEqual(['cn', 'hk', 'us']);
    expect(parseMarketReviewRegionTokens('both')).toEqual(['cn', 'hk', 'us', 'jp', 'kr']);
    expect(parseMarketReviewRegionTokens('us,cn,bogus,us')).toEqual(['cn', 'us']);
    expect(parseMarketReviewRegionTokens('')).toEqual([]);
  });

  it('formats token strings with localized labels and locale list separators', () => {
    const getLabel = (region: keyof typeof zhLabels) => zhLabels[region];
    expect(formatMarketReviewRegionLabels('cn,hk', getLabel, 'zh')).toContain('A 股');
    expect(formatMarketReviewRegionLabels('cn,hk', getLabel, 'zh')).toContain('港股');
    expect(formatMarketReviewRegionLabels('cn,hk', getLabel, 'zh')).not.toMatch(/\bcn\b/);
    expect(formatMarketReviewRegionLabels('unknown-token', getLabel, 'en')).toBe('unknown-token');
  });

  it('formats explicit selections with the same label source', () => {
    const getLabel = (region: keyof typeof zhLabels) => zhLabels[region];
    const formatted = formatMarketReviewRegionSelection(['us', 'cn'], getLabel, 'zh');
    expect(formatted).toContain('A 股');
    expect(formatted).toContain('美股');
  });
});
