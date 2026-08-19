// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  DATATABLE_DEFAULT_ROW_HEIGHT_PX,
  DATATABLE_OVERSCAN,
  DATATABLE_VIRTUALIZE_THRESHOLD,
  DATATABLE_VIRTUAL_VIEWPORT_PX,
} from '../../../performance/runtimeBudgets';
import {
  estimatedDataTableRowHeight,
  findBoundedVerticalScrollParent,
  resolveDataTableViewportCap,
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

  it('caps the viewport to a tighter overflow parent', () => {
    const parent = document.createElement('div');
    parent.style.overflowY = 'auto';
    parent.style.maxHeight = '240px';
    const child = document.createElement('div');
    parent.append(child);
    document.body.append(parent);

    expect(findBoundedVerticalScrollParent(child, DATATABLE_VIRTUAL_VIEWPORT_PX)).toBe(parent);
    expect(resolveDataTableViewportCap(child, DATATABLE_VIRTUAL_VIEWPORT_PX)).toBe(240);

    parent.remove();
  });

  it('ignores a page-level scroller taller than the self viewport', () => {
    const parent = document.createElement('div');
    parent.style.overflowY = 'auto';
    Object.defineProperty(parent, 'clientHeight', { configurable: true, value: 800 });
    const child = document.createElement('div');
    parent.append(child);
    document.body.append(parent);

    expect(findBoundedVerticalScrollParent(child, DATATABLE_VIRTUAL_VIEWPORT_PX)).toBeNull();
    expect(resolveDataTableViewportCap(child, DATATABLE_VIRTUAL_VIEWPORT_PX))
      .toBe(DATATABLE_VIRTUAL_VIEWPORT_PX);

    parent.remove();
  });

  it('walks past a looser overflow ancestor to a tighter scroller further up', () => {
    const outer = document.createElement('div');
    outer.style.overflowY = 'auto';
    outer.style.maxHeight = '240px';
    const inner = document.createElement('div');
    inner.style.overflowY = 'auto';
    Object.defineProperty(inner, 'clientHeight', { configurable: true, value: 800 });
    const child = document.createElement('div');
    inner.append(child);
    outer.append(inner);
    document.body.append(outer);

    expect(findBoundedVerticalScrollParent(child, DATATABLE_VIRTUAL_VIEWPORT_PX)).toBe(outer);
    expect(resolveDataTableViewportCap(child, DATATABLE_VIRTUAL_VIEWPORT_PX)).toBe(240);

    outer.remove();
  });

  it('walks past overflow-hidden frames to the tighter scroller', () => {
    const scroller = document.createElement('div');
    scroller.style.overflowY = 'auto';
    scroller.style.maxHeight = '288px';
    const frame = document.createElement('div');
    frame.style.overflow = 'hidden';
    const child = document.createElement('div');
    frame.append(child);
    scroller.append(frame);
    document.body.append(scroller);

    expect(findBoundedVerticalScrollParent(child, DATATABLE_VIRTUAL_VIEWPORT_PX)).toBe(scroller);
    expect(resolveDataTableViewportCap(child, DATATABLE_VIRTUAL_VIEWPORT_PX)).toBe(288);

    scroller.remove();
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
