import { describe, expect, it, vi } from 'vitest';
import { isDialogFocusableElement } from '../useDialogA11y';

describe('isDialogFocusableElement', () => {
  it('keeps a visible fixed-position control in the dialog focus order', () => {
    const button = document.createElement('button');
    button.style.position = 'fixed';
    document.body.appendChild(button);
    Object.defineProperty(button, 'offsetParent', { configurable: true, value: null });
    vi.spyOn(button, 'getClientRects').mockReturnValue([new DOMRect(10, 10, 44, 44)] as unknown as DOMRectList);

    expect(isDialogFocusableElement(button)).toBe(true);
    button.remove();
  });

  it('excludes controls hidden by an ancestor', () => {
    const wrapper = document.createElement('div');
    wrapper.hidden = true;
    const button = document.createElement('button');
    wrapper.appendChild(button);
    document.body.appendChild(wrapper);
    vi.spyOn(button, 'getClientRects').mockReturnValue([new DOMRect(10, 10, 44, 44)] as unknown as DOMRectList);

    expect(isDialogFocusableElement(button)).toBe(false);
    wrapper.remove();
  });
});
