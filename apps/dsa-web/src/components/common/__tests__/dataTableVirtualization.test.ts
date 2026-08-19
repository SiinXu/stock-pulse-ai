// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  DATATABLE_DEFAULT_ROW_HEIGHT_PX,
  DATATABLE_OVERSCAN,
  DATATABLE_VIRTUALIZE_THRESHOLD,
} from '../../../performance/runtimeBudgets';
import {
  estimatedDataTableRowHeight,
  resolveDataTableVirtualization,
} from '../dataTableVirtualization';

describe('resolveDataTableVirtualization', () => {
  it('keeps small tables fully mounted', () => {
    expect(resolveDataTableVirtualization({
      rowCount: DATATABLE_VIRTUALIZE_THRESHOLD - 1,
      hasRowDetails: false,
      density: 'default',
    })).toMatchObject({
      enabled: false,
      reason: 'below-threshold',
      rowHeight: DATATABLE_DEFAULT_ROW_HEIGHT_PX,
      overscan: DATATABLE_OVERSCAN,
      threshold: DATATABLE_VIRTUALIZE_THRESHOLD,
    });
  });

  it('windows tables at the measured threshold', () => {
    expect(resolveDataTableVirtualization({
      rowCount: DATATABLE_VIRTUALIZE_THRESHOLD,
      hasRowDetails: false,
      density: 'compact',
    })).toMatchObject({
      enabled: true,
      reason: 'windowed',
      rowHeight: estimatedDataTableRowHeight('compact'),
    });
  });

  it('falls back for controlled detail rows and explicit opt-out', () => {
    expect(resolveDataTableVirtualization({
      rowCount: 80,
      hasRowDetails: true,
      density: 'default',
    })).toMatchObject({ enabled: false, reason: 'row-details' });

    expect(resolveDataTableVirtualization({
      rowCount: 80,
      hasRowDetails: false,
      density: 'default',
      virtualization: false,
    })).toMatchObject({ enabled: false, reason: 'disabled' });
  });

  it('accepts verified row-height and overscan overrides', () => {
    expect(resolveDataTableVirtualization({
      rowCount: 80,
      hasRowDetails: false,
      density: 'default',
      virtualization: { rowHeight: 64, overscan: 8, threshold: 40, viewportMaxHeight: 320 },
    })).toMatchObject({
      enabled: true,
      reason: 'windowed',
      rowHeight: 64,
      overscan: 8,
      threshold: 40,
      viewportMaxHeight: 320,
    });
  });
});
