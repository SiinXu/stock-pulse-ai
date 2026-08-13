import { useCallback, useMemo, useState, type UIEvent } from 'react';

export type VirtualWindowRange = {
  startIndex: number;
  endIndex: number;
  offsetTop: number;
  offsetBottom: number;
  totalHeight: number;
};

export type UseVirtualWindowOptions = {
  itemCount: number;
  estimatedItemHeight: number;
  overscan?: number;
  enabled?: boolean;
  initialScrollTop?: number;
};

/**
 * Lightweight fixed-estimate vertical windowing without an extra dependency.
 * Callers place top/bottom spacers and map only `startIndex..endIndex` items.
 */
export function useVirtualWindow({
  itemCount,
  estimatedItemHeight,
  overscan = 4,
  enabled = true,
  initialScrollTop = 0,
}: UseVirtualWindowOptions): {
  range: VirtualWindowRange;
  onScroll: (event: UIEvent<HTMLElement>) => void;
  scrollTop: number;
  setViewportHeight: (height: number) => void;
} {
  const [scrollTop, setScrollTop] = useState(initialScrollTop);
  const [viewportHeight, setViewportHeight] = useState(0);

  const onScroll = useCallback((event: UIEvent<HTMLElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  }, []);

  const range = useMemo<VirtualWindowRange>(() => {
    const totalHeight = Math.max(0, itemCount * estimatedItemHeight);
    if (!enabled || itemCount === 0) {
      return {
        startIndex: 0,
        endIndex: Math.max(0, itemCount - 1),
        offsetTop: 0,
        offsetBottom: 0,
        totalHeight,
      };
    }

    const safeHeight = estimatedItemHeight > 0 ? estimatedItemHeight : 1;
    const visibleCount = Math.max(1, Math.ceil((viewportHeight || safeHeight) / safeHeight));
    const rawStart = Math.floor(scrollTop / safeHeight);
    const startIndex = Math.max(0, rawStart - overscan);
    const endIndex = Math.min(itemCount - 1, rawStart + visibleCount + overscan);
    const offsetTop = startIndex * safeHeight;
    const offsetBottom = Math.max(0, (itemCount - endIndex - 1) * safeHeight);

    return {
      startIndex,
      endIndex,
      offsetTop,
      offsetBottom,
      totalHeight,
    };
  }, [enabled, estimatedItemHeight, itemCount, overscan, scrollTop, viewportHeight]);

  return {
    range,
    onScroll,
    scrollTop,
    setViewportHeight,
  };
}
