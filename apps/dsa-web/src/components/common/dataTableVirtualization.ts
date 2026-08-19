// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import {
  DATATABLE_COMPACT_ROW_HEIGHT_PX,
  DATATABLE_DEFAULT_ROW_HEIGHT_PX,
  DATATABLE_OVERSCAN,
  DATATABLE_VIRTUAL_VIEWPORT_PX,
  DATATABLE_VIRTUALIZE_THRESHOLD,
} from '../../performance/runtimeBudgets';

type DataTableDensity = 'compact' | 'default';

export type DataTableVirtualizationReason =
  | 'windowed'
  | 'below-threshold'
  | 'row-details'
  | 'disabled';

export type DataTableVirtualizationConfig = {
  threshold?: number;
  rowHeight?: number;
  overscan?: number;
  viewportMaxHeight?: number;
};

export type DataTableVirtualizationProp = false | DataTableVirtualizationConfig;

export type ResolvedDataTableVirtualization = {
  enabled: boolean;
  reason: DataTableVirtualizationReason;
  threshold: number;
  rowHeight: number;
  overscan: number;
  viewportMaxHeight: number;
};

function positiveInt(value: number | undefined, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? Math.floor(value)
    : fallback;
}

export function estimatedDataTableRowHeight(density: DataTableDensity): number {
  return density === 'compact'
    ? DATATABLE_COMPACT_ROW_HEIGHT_PX
    : DATATABLE_DEFAULT_ROW_HEIGHT_PX;
}

/**
 * Shared DataTable virtualization decision.
 * Auto-window only above the measured threshold when row height is the
 * shared fixed estimate. Detail rows and explicit `virtualization={false}`
 * keep the full native table. Callers whose cells wrap, stack, or list
 * must opt out; auto mode does not measure rendered height.
 */
export function resolveDataTableVirtualization(input: {
  rowCount: number;
  hasRowDetails: boolean;
  density: DataTableDensity;
  virtualization?: DataTableVirtualizationProp;
}): ResolvedDataTableVirtualization {
  const config = input.virtualization === false ? undefined : input.virtualization;
  const threshold = positiveInt(config?.threshold, DATATABLE_VIRTUALIZE_THRESHOLD);
  const rowHeight = positiveInt(config?.rowHeight, estimatedDataTableRowHeight(input.density));
  const overscan = positiveInt(config?.overscan, DATATABLE_OVERSCAN);
  const viewportMaxHeight = positiveInt(config?.viewportMaxHeight, DATATABLE_VIRTUAL_VIEWPORT_PX);

  if (input.virtualization === false) {
    return {
      enabled: false,
      reason: 'disabled',
      threshold,
      rowHeight,
      overscan,
      viewportMaxHeight,
    };
  }

  if (input.hasRowDetails) {
    return {
      enabled: false,
      reason: 'row-details',
      threshold,
      rowHeight,
      overscan,
      viewportMaxHeight,
    };
  }

  if (input.rowCount < threshold) {
    return {
      enabled: false,
      reason: 'below-threshold',
      threshold,
      rowHeight,
      overscan,
      viewportMaxHeight,
    };
  }

  return {
    enabled: true,
    reason: 'windowed',
    threshold,
    rowHeight,
    overscan,
    viewportMaxHeight,
  };
}

function usedVerticalBoundPx(element: HTMLElement): number {
  if (element.clientHeight > 0) {
    return element.clientHeight;
  }
  const { maxHeight } = window.getComputedStyle(element);
  if (!maxHeight.endsWith('px')) {
    return 0;
  }
  const parsed = Number.parseFloat(maxHeight);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

/**
 * Nearest ancestor that already owns a tighter vertical scrollport than the
 * DataTable self viewport. Page-level fillers (for example Shell main) are
 * taller than the default cap and must not steal the table's own scroller.
 */
export function findBoundedVerticalScrollParent(
  element: HTMLElement,
  maxSelfViewport: number,
): HTMLElement | null {
  let current = element.parentElement;
  while (
    current
    && current !== document.body
    && current !== document.documentElement
  ) {
    const overflowY = window.getComputedStyle(current).overflowY;
    if (overflowY === 'auto' || overflowY === 'scroll') {
      const bound = usedVerticalBoundPx(current);
      if (bound > 0 && bound < maxSelfViewport) {
        return current;
      }
    }
    current = current.parentElement;
  }
  return null;
}

/** Cap the windowed table to a tighter parent scroller so the two do not nest. */
export function resolveDataTableViewportCap(
  element: HTMLElement,
  maxSelfViewport: number,
): number {
  const parent = findBoundedVerticalScrollParent(element, maxSelfViewport);
  if (!parent) {
    return maxSelfViewport;
  }
  const bound = usedVerticalBoundPx(parent);
  return bound > 0 && bound < maxSelfViewport ? bound : maxSelfViewport;
}
