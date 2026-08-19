// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useVirtualWindow } from '../useVirtualWindow';

describe('useVirtualWindow', () => {
  it('returns the full range when disabled or empty', () => {
    const disabled = renderHook(() => useVirtualWindow({
      itemCount: 40,
      estimatedItemHeight: 48,
      enabled: false,
    }));
    expect(disabled.result.current.range).toMatchObject({
      startIndex: 0,
      endIndex: 39,
      offsetTop: 0,
      offsetBottom: 0,
      totalHeight: 1920,
    });

    const empty = renderHook(() => useVirtualWindow({
      itemCount: 0,
      estimatedItemHeight: 48,
    }));
    expect(empty.result.current.range).toMatchObject({
      startIndex: 0,
      endIndex: 0,
      offsetTop: 0,
      offsetBottom: 0,
      totalHeight: 0,
    });
  });

  it('windows the first and last items with correct spacer geometry', () => {
    const first = renderHook(() => useVirtualWindow({
      itemCount: 150,
      estimatedItemHeight: 48,
      overscan: 6,
      initialScrollTop: 0,
    }));
    act(() => {
      first.result.current.setViewportHeight(480);
    });
    expect(first.result.current.range.startIndex).toBe(0);
    expect(first.result.current.range.offsetTop).toBe(0);
    expect(first.result.current.range.endIndex).toBeLessThan(149);
    expect(first.result.current.range.offsetBottom).toBe(
      (150 - first.result.current.range.endIndex - 1) * 48,
    );
    expect(
      first.result.current.range.offsetTop
      + ((first.result.current.range.endIndex - first.result.current.range.startIndex + 1) * 48)
      + first.result.current.range.offsetBottom,
    ).toBe(150 * 48);

    const last = renderHook(() => useVirtualWindow({
      itemCount: 150,
      estimatedItemHeight: 48,
      overscan: 6,
      initialScrollTop: 149 * 48,
    }));
    act(() => {
      last.result.current.setViewportHeight(480);
    });
    expect(last.result.current.range.endIndex).toBe(149);
    expect(last.result.current.range.offsetBottom).toBe(0);
    expect(last.result.current.range.startIndex).toBeGreaterThan(0);
    expect(
      last.result.current.range.offsetTop
      + ((last.result.current.range.endIndex - last.result.current.range.startIndex + 1) * 48)
      + last.result.current.range.offsetBottom,
    ).toBe(150 * 48);
  });

  it('clamps a stale scroll offset after the item count shrinks', () => {
    const { result, rerender } = renderHook(
      ({ itemCount }) => useVirtualWindow({
        itemCount,
        estimatedItemHeight: 48,
        overscan: 6,
        initialScrollTop: 10_000,
      }),
      { initialProps: { itemCount: 80 } },
    );
    act(() => {
      result.current.setViewportHeight(480);
    });
    expect(result.current.range.endIndex).toBe(79);

    rerender({ itemCount: 30 });
    expect(result.current.range.endIndex).toBe(29);
    expect(result.current.range.startIndex).toBeGreaterThanOrEqual(0);
    expect(result.current.range.startIndex).toBeLessThanOrEqual(result.current.range.endIndex);
  });
});
