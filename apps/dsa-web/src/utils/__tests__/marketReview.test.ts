import { describe, expect, it } from 'vitest';
import { getMarketLightColor } from '../marketReview';

describe('getMarketLightColor', () => {
  it.each([
    [0, '#ef4444'],
    [39, '#ef4444'],
    [40, '#eab308'],
    [59, '#eab308'],
    [60, '#22c55e'],
    [100, '#22c55e'],
  ])('maps score %s to the canonical traffic-light color', (score, expected) => {
    expect(getMarketLightColor(score)).toBe(expected);
  });
});
