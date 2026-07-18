// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Modal } from '../../common/Modal';
import { FIXED_POPUP_VIEWPORT_MARGIN_PX } from '../../common/useFixedPopup';
import { MultiSelectDropdown } from '../MultiSelectDropdown';

const options = [
  { value: 'a', label: 'Alpha' },
  { value: 'b', label: 'Beta' },
  { value: 'c', label: 'Gamma' },
];

const tabForward = () => {
  const current = document.activeElement as HTMLElement | null;
  if (!current || !fireEvent.keyDown(current, { key: 'Tab' })) {
    return;
  }
  const tabStops = Array.from(document.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
  ));
  const currentIndex = tabStops.indexOf(current);
  tabStops[currentIndex + 1]?.focus();
  fireEvent.keyUp(current, { key: 'Tab' });
};

describe('MultiSelectDropdown', () => {
  it('keeps options collapsed behind a trigger and serializes toggles in catalog order', () => {
    const onChange = vi.fn();
    render(<MultiSelectDropdown options={options} selected={['c']} onChange={onChange} />);

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    const trigger = screen.getByRole('button', { name: /已选/ });
    expect(trigger).toHaveTextContent('已选 1 / 3');
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');

    fireEvent.click(trigger);
    const listbox = screen.getByRole('listbox');
    const checkboxes = within(listbox).getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(3);
    // Below the threshold the popup has no search box.
    expect(screen.queryByLabelText('搜索选项')).not.toBeInTheDocument();

    // Selecting a serializes in catalog order, not click order.
    fireEvent.click(checkboxes[0]);
    expect(onChange).toHaveBeenCalledWith(['a', 'c']);
  });

  it('moves focus into a compact popup before subsequent Tab navigation', () => {
    render(
      <>
        <MultiSelectDropdown options={options} selected={[]} onChange={vi.fn()} />
        <button type="button">Later page control</button>
      </>,
    );

    const trigger = screen.getByRole('button', { name: /已选/ });
    trigger.focus();
    fireEvent.click(trigger);

    const [firstOption, secondOption] = within(screen.getByRole('listbox')).getAllByRole('checkbox');
    expect(firstOption).toHaveFocus();

    tabForward();
    expect(secondOption).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Later page control' })).not.toHaveFocus();
  });

  it('keeps unknown selected values visible, counted, and removable', () => {
    const onChange = vi.fn();
    render(<MultiSelectDropdown options={options} selected={['b', 'mystery']} onChange={onChange} />);

    expect(screen.getByRole('button', { name: /已选/ })).toHaveTextContent('已选 2 / 4');
    expect(screen.getByText('mystery')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '移除 mystery' }));
    expect(onChange).toHaveBeenCalledWith(['b']);
  });

  it('appends picks in selection order and shows priority positions when ordered', () => {
    const onChange = vi.fn();
    render(<MultiSelectDropdown options={options} selected={['c', 'a']} onChange={onChange} ordered />);

    // Chips carry priority positions in ordered mode.
    expect(screen.getByText('1. Gamma')).toBeInTheDocument();
    expect(screen.getByText('2. Alpha')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /已选/ }));
    expect(screen.getByText('优先级 1')).toBeInTheDocument();
    expect(screen.getByText('优先级 2')).toBeInTheDocument();

    // New picks append to the tail instead of re-sorting to catalog order.
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]);
    expect(onChange).toHaveBeenCalledWith(['c', 'a', 'b']);
  });

  it('deselecting in ordered mode removes the value while keeping the rest in order', () => {
    const onChange = vi.fn();
    render(<MultiSelectDropdown options={options} selected={['c', 'a', 'b']} onChange={onChange} ordered />);

    fireEvent.click(screen.getByRole('button', { name: /已选/ }));
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]); // deselect a
    expect(onChange).toHaveBeenCalledWith(['c', 'b']);
  });

  it('shows a search box past the threshold and filters by label or value', () => {
    const many = ['a', 'b', 'c', 'd', 'e', 'f'].map((value) => ({
      value,
      label: `L-${value.toUpperCase()}`,
    }));
    render(<MultiSelectDropdown options={many} selected={[]} onChange={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /已选/ }));
    const search = screen.getByLabelText('搜索选项');
    const listbox = screen.getByRole('listbox');
    expect(search).toHaveFocus();

    fireEvent.change(search, { target: { value: 'l-f' } });
    expect(within(listbox).getAllByRole('option')).toHaveLength(1);
    expect(within(listbox).getByText('L-F')).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'zzz' } });
    expect(within(listbox).queryAllByRole('option')).toHaveLength(0);
    expect(within(listbox).getByText('无匹配选项')).toBeInTheDocument();
  });

  it('tabs from search into the first option without closing the popup', () => {
    const many = ['a', 'b', 'c', 'd', 'e', 'f'].map((value) => ({
      value,
      label: `L-${value.toUpperCase()}`,
    }));
    render(<MultiSelectDropdown options={many} selected={[]} onChange={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /已选/ }));
    const search = screen.getByLabelText('搜索选项');
    expect(search).toHaveFocus();

    tabForward();

    const listbox = screen.getByRole('listbox');
    expect(listbox).toBeInTheDocument();
    expect(within(listbox).getAllByRole('checkbox')[0]).toHaveFocus();
  });

  it('selects a focused option with Enter', () => {
    const many = ['a', 'b', 'c', 'd', 'e', 'f'].map((value) => ({
      value,
      label: `L-${value.toUpperCase()}`,
    }));
    const onChange = vi.fn();
    render(<MultiSelectDropdown options={many} selected={[]} onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: /已选/ }));
    tabForward();
    const firstOption = within(screen.getByRole('listbox')).getAllByRole('checkbox')[0];
    expect(firstOption).toHaveFocus();

    fireEvent.keyDown(firstOption, { key: 'Enter' });

    expect(onChange).toHaveBeenCalledWith(['a']);
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('closes and returns focus to the trigger when Tab leaves the last option', () => {
    const many = ['a', 'b', 'c', 'd', 'e', 'f'].map((value) => ({
      value,
      label: `L-${value.toUpperCase()}`,
    }));
    render(<MultiSelectDropdown options={many} selected={[]} onChange={vi.fn()} />);

    const trigger = screen.getByRole('button', { name: /已选/ });
    fireEvent.click(trigger);
    const lastOption = within(screen.getByRole('listbox')).getAllByRole('checkbox').at(-1);
    expect(lastOption).toBeDefined();
    lastOption?.focus();

    const shouldContinueNativeTab = fireEvent.keyDown(lastOption as HTMLElement, { key: 'Tab' });

    expect(shouldContinueNativeTab).toBe(false);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('moves focus from the first option back to search with Shift+Tab', () => {
    const many = ['a', 'b', 'c', 'd', 'e', 'f'].map((value) => ({
      value,
      label: `L-${value.toUpperCase()}`,
    }));
    render(<MultiSelectDropdown options={many} selected={[]} onChange={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /已选/ }));
    const search = screen.getByLabelText('搜索选项');
    tabForward();
    const firstOption = within(screen.getByRole('listbox')).getAllByRole('checkbox')[0];
    expect(firstOption).toHaveFocus();

    const shouldContinueNativeTab = fireEvent.keyDown(firstOption, {
      key: 'Tab',
      shiftKey: true,
    });

    expect(shouldContinueNativeTab).toBe(false);
    expect(search).toHaveFocus();
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('returns focus to the trigger when Shift+Tab leaves search', () => {
    const many = ['a', 'b', 'c', 'd', 'e', 'f'].map((value) => ({
      value,
      label: `L-${value.toUpperCase()}`,
    }));
    render(<MultiSelectDropdown options={many} selected={[]} onChange={vi.fn()} />);

    const trigger = screen.getByRole('button', { name: /已选/ });
    fireEvent.click(trigger);
    const search = screen.getByLabelText('搜索选项');
    expect(search).toHaveFocus();

    fireEvent.keyDown(search, { key: 'Tab', shiftKey: true });

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('keeps the popup open across a transient disabled flip (settings autosave)', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <MultiSelectDropdown options={options} selected={['a']} onChange={onChange} />,
    );

    fireEvent.click(screen.getByRole('button', { name: /已选/ }));
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    // Settings autosave briefly disables every field after each change; the
    // popup must survive the flip so multi-picking is not one-click-per-open.
    rerender(<MultiSelectDropdown options={options} selected={['a']} onChange={onChange} disabled />);
    const listbox = screen.getByRole('listbox');
    within(listbox).getAllByRole('checkbox').forEach((checkbox) => expect(checkbox).toBeDisabled());

    rerender(<MultiSelectDropdown options={options} selected={['a']} onChange={onChange} />);
    fireEvent.click(within(screen.getByRole('listbox')).getAllByRole('checkbox')[1]);
    expect(onChange).toHaveBeenCalledWith(['a', 'b']);
  });

  it('restores option focus after an autosave disabled flip drops focus to the body', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <MultiSelectDropdown options={options} selected={['a']} onChange={onChange} />,
    );

    fireEvent.click(screen.getByRole('button', { name: /已选/ }));
    const secondOption = within(screen.getByRole('listbox')).getAllByRole('checkbox')[1];
    secondOption.focus();
    expect(secondOption).toHaveFocus();

    rerender(
      <MultiSelectDropdown options={options} selected={['a']} onChange={onChange} disabled />,
    );
    document.body.tabIndex = -1;
    document.body.focus();
    document.body.removeAttribute('tabindex');
    expect(document.body).toHaveFocus();

    rerender(<MultiSelectDropdown options={options} selected={['a']} onChange={onChange} />);

    const restoredOption = within(screen.getByRole('listbox')).getAllByRole('checkbox')[1];
    expect(restoredOption).toHaveFocus();
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('closes on Escape and restores focus to the trigger', () => {
    render(<MultiSelectDropdown options={options} selected={[]} onChange={vi.fn()} />);

    const trigger = screen.getByRole('button', { name: /已选/ });
    trigger.focus();
    fireEvent.click(trigger);
    const firstOption = within(screen.getByRole('listbox')).getAllByRole('checkbox')[0];
    expect(firstOption).toHaveFocus();

    fireEvent.keyDown(document.activeElement as HTMLElement, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('portals and positions a bottom-anchored popup inside the viewport', async () => {
    const triggerRect = new DOMRect(110, 706, 272, 44);
    const popupRect = new DOMRect(110, 754, 348, 299);
    const rectSpy = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockImplementation(function getBoundingClientRect(this: HTMLElement) {
        if (this.getAttribute('aria-label') === '通知渠道') {
          return triggerRect;
        }
        if (this.getAttribute('data-dialog-popup') === 'true') {
          return popupRect;
        }
        return new DOMRect();
      });
    vi.stubGlobal('innerWidth', 390);
    vi.stubGlobal('innerHeight', 844);

    try {
      render(
        <Modal isOpen title="通知设置" onClose={() => {}}>
          <div data-testid="clipping-parent" className="overflow-hidden">
            <MultiSelectDropdown
              options={options}
              selected={[]}
              onChange={() => {}}
              ariaLabel="通知渠道"
            />
          </div>
        </Modal>,
      );
      const dialog = screen.getByRole('dialog', { name: '通知设置' });
      const clippingParent = screen.getByTestId('clipping-parent');
      fireEvent.click(within(dialog).getByRole('button', { name: '通知渠道' }));
      const popup = screen.getByRole('listbox', { name: '通知渠道' }).parentElement;
      expect(popup).not.toBeNull();

      await waitFor(() => {
        expect(popup).toHaveClass('fixed');
        expect(popup?.parentElement).toBe(dialog);
        expect(clippingParent).not.toContainElement(popup);
        expect(popup?.style.maxWidth).toBe(
          `calc(100vw - ${FIXED_POPUP_VIEWPORT_MARGIN_PX * 2}px)`,
        );

        const popupTop = Number.parseFloat(popup?.style.top ?? '');
        const popupLeft = Number.parseFloat(popup?.style.left ?? '');
        expect(popupTop).toBeLessThan(triggerRect.top);
        expect(popupTop + popupRect.height).toBeLessThanOrEqual(
          window.innerHeight - FIXED_POPUP_VIEWPORT_MARGIN_PX,
        );
        expect(popupLeft).toBeGreaterThanOrEqual(FIXED_POPUP_VIEWPORT_MARGIN_PX);
        expect(popupLeft + popupRect.width).toBeLessThanOrEqual(
          window.innerWidth - FIXED_POPUP_VIEWPORT_MARGIN_PX,
        );
      });
    } finally {
      rectSpy.mockRestore();
      vi.unstubAllGlobals();
    }
  });
});
