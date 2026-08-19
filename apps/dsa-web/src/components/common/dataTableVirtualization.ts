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
 * Auto-window only above the measured threshold. Detail rows (variable extra
 * height) and explicit `virtualization={false}` keep the full native table.
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
