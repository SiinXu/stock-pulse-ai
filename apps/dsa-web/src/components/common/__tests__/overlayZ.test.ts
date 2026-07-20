// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { getOverlayStyle, OVERLAY_Z } from '../overlayZ';

describe('overlay layer authority', () => {
  it('overrides caller z-index while retaining geometry', () => {
    expect(getOverlayStyle('popover', { top: 12, left: 24, zIndex: 1 })).toEqual({
      top: 12,
      left: 24,
      zIndex: OVERLAY_Z.popover,
    });
  });

  it('keeps transient feedback below confirmations and above dialog content', () => {
    expect(OVERLAY_Z.popover).toBeGreaterThan(OVERLAY_Z.dialog);
    expect(OVERLAY_Z.toast).toBeGreaterThan(OVERLAY_Z.tooltip);
    expect(OVERLAY_Z.toast).toBeLessThan(OVERLAY_Z.confirmation);
  });
});
