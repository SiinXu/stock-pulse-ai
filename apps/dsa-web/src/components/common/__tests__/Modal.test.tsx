// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ConfirmDialog } from '../ConfirmDialog';
import { Modal } from '../Modal';
import { Select } from '../Select';

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

const OPTIONS = [
  { value: 'a', label: '选项 A' },
  { value: 'b', label: '选项 B' },
];

function renderModalWithSelect() {
  const onClose = vi.fn();
  render(
    <UiLanguageProvider>
      <Modal isOpen onClose={onClose} title="测试弹窗">
        <Select value="a" onChange={() => undefined} options={OPTIONS} ariaLabel="测试下拉" />
      </Modal>
    </UiLanguageProvider>,
  );
  return { onClose };
}

describe('Modal escape behavior', () => {
  it('keeps header, scrollable body, and footer as separate layout slots', () => {
    render(
      <UiLanguageProvider>
        <Modal
          isOpen
          onClose={() => undefined}
          title="Edit connection"
          description="Connection details"
          footer={<button type="button">Save connection</button>}
        >
          <p>Connection form</p>
        </Modal>
      </UiLanguageProvider>,
    );

    const dialog = screen.getByRole('dialog', { name: 'Edit connection' });
    expect(dialog).toHaveAttribute('data-modal-size', 'default');
    expect(dialog.querySelector('[data-overlay-slot="header"]')).toHaveTextContent('Connection details');
    expect(dialog.querySelector('[data-overlay-slot="body"]')).toHaveTextContent('Connection form');
    expect(dialog.querySelector('[data-overlay-slot="footer"]')).toContainElement(
      screen.getByRole('button', { name: 'Save connection' }),
    );
  });

  it('blocks backdrop, Escape, and close-button dismissal while closing is disabled', () => {
    const onClose = vi.fn();
    render(
      <UiLanguageProvider>
        <Modal
          isOpen
          closeDisabled
          onClose={onClose}
          title="保存中"
          description="保存完成前不能关闭"
        >
          <p>正在保存</p>
        </Modal>
      </UiLanguageProvider>,
    );

    const dialog = screen.getByRole('dialog', { name: '保存中' });
    expect(dialog).toHaveAccessibleDescription('保存完成前不能关闭');
    const root = dialog.closest<HTMLElement>('[data-overlay-root]');
    fireEvent.click(root as HTMLElement);
    fireEvent.keyDown(dialog, { key: 'Escape' });
    fireEvent.click(within(dialog).getByRole('button'));

    expect(within(dialog).getByRole('button')).toBeDisabled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('isolates the application while open and restores focus after closing', () => {
    const Harness = () => {
      const [isOpen, setIsOpen] = useState(false);
      return (
        <UiLanguageProvider>
          <button type="button" onClick={() => setIsOpen(true)}>打开弹窗</button>
          <Modal isOpen={isOpen} onClose={() => setIsOpen(false)} title="测试弹窗">
            <p>弹窗内容</p>
          </Modal>
        </UiLanguageProvider>
      );
    };

    const { container } = render(<Harness />);
    const trigger = screen.getByRole('button', { name: '打开弹窗' });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole('dialog', { name: '测试弹窗' });
    expect(container).toHaveAttribute('inert');
    expect(container).toHaveAttribute('aria-hidden', 'true');
    expect(dialog).toContainElement(document.activeElement as HTMLElement);

    fireEvent.click(within(dialog).getByRole('button'));

    expect(container).not.toHaveAttribute('inert');
    expect(container).not.toHaveAttribute('aria-hidden');
    expect(trigger).toHaveFocus();
  });

  it('closes on Escape when no popup is open inside', () => {
    const { onClose } = renderModalWithSelect();

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('lets an open Select consume Escape before closing the modal', () => {
    const { onClose } = renderModalWithSelect();
    const trigger = screen.getByRole('combobox', { name: '测试下拉' });

    fireEvent.click(trigger);
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    fireEvent.keyDown(trigger, { key: 'Escape' });

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.keyDown(trigger, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes only the topmost surface when dialogs are stacked', () => {
    const onClose = vi.fn();
    const onCancel = vi.fn();
    const renderTree = (confirmOpen: boolean) => (
      <UiLanguageProvider>
        <Modal isOpen onClose={onClose} title="外层弹窗">
          <ConfirmDialog
            isOpen={confirmOpen}
            title="确认操作"
            message="确定吗？"
            onConfirm={vi.fn()}
            onCancel={onCancel}
          />
        </Modal>
      </UiLanguageProvider>
    );
    // The confirm opens after the modal (as it does in real usage), so it
    // becomes the topmost surface on the shared dialog stack.
    const { rerender } = render(renderTree(false));
    rerender(renderTree(true));

    const outerDialog = screen.getByRole('dialog', { name: '外层弹窗', hidden: true });
    const confirmDialog = screen.getByRole('dialog', { name: '确认操作' });
    expect(outerDialog.closest('[data-overlay-root]')).toHaveAttribute('inert');
    expect(outerDialog.closest('[data-overlay-root]')).toHaveAttribute('aria-hidden', 'true');
    expect(confirmDialog.closest('[data-overlay-root]')).not.toHaveAttribute('inert');

    outerDialog.focus();
    fireEvent.keyDown(document.body, { key: 'Tab' });
    expect(confirmDialog).toHaveFocus();

    // Escape must close the topmost dialog (the confirm) only, not the modal.
    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('restores focus inside the underlying modal after closing a confirmation', () => {
    const Harness = () => {
      const [confirmOpen, setConfirmOpen] = useState(false);
      return (
        <UiLanguageProvider>
          <Modal isOpen onClose={() => undefined} title="外层弹窗">
            <button type="button" onClick={() => setConfirmOpen(true)}>打开确认</button>
            <ConfirmDialog
              isOpen={confirmOpen}
              title="确认操作"
              message="确定吗？"
              onConfirm={() => undefined}
              onCancel={() => setConfirmOpen(false)}
            />
          </Modal>
        </UiLanguageProvider>
      );
    };

    render(<Harness />);
    const trigger = screen.getByRole('button', { name: '打开确认' });
    trigger.focus();
    fireEvent.click(trigger);

    const confirmation = screen.getByRole('dialog', { name: '确认操作' });
    expect(confirmation).toHaveAccessibleDescription('确定吗？');
    fireEvent.keyDown(confirmation, { key: 'Escape' });

    expect(screen.queryByRole('dialog', { name: '确认操作' })).not.toBeInTheDocument();
    const outer = screen.getByRole('dialog', { name: '外层弹窗' });
    expect(outer.closest('[data-overlay-root]')).not.toHaveAttribute('inert');
    expect(trigger).toHaveFocus();
  });
});
