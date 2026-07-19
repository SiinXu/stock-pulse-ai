import { describe, expect, it } from 'vitest';
import { getOverlayStyle, OVERLAY_Z } from '../overlayZ';

describe('overlayZ', () => {
  it('applies the authoritative layer without dropping positioning styles', () => {
    expect(getOverlayStyle('dropdown', { top: 12, left: 24, zIndex: 1 })).toEqual({
      top: 12,
      left: 24,
      zIndex: OVERLAY_Z.dropdown,
    });
  });

  it('keeps transient feedback below confirmations and above other overlays', () => {
    expect(OVERLAY_Z.toast).toBeGreaterThan(OVERLAY_Z.settingsModal);
    expect(OVERLAY_Z.toast).toBeLessThan(OVERLAY_Z.confirm);
  });
});
