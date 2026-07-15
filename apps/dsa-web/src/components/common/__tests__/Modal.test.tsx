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

    // Escape must close the topmost dialog (the confirm) only, not the modal.
    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('makes the background inert and restores focus after closing', () => {
    const Harness = () => {
      const [open, setOpen] = useState(false);
      return (
        <UiLanguageProvider>
          <button type="button" onClick={() => setOpen(true)}>打开弹窗</button>
          <div data-testid="background-content">背景内容</div>
          <Modal isOpen={open} onClose={() => setOpen(false)} title="焦点弹窗">
            <button type="button">弹窗操作</button>
          </Modal>
        </UiLanguageProvider>
      );
    };
    render(<Harness />);

    const trigger = screen.getByRole('button', { name: '打开弹窗' });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole('dialog', { name: '焦点弹窗' });
    expect(dialog.closest('[data-overlay-root="modal"]')).toBeInTheDocument();
    expect(screen.getByTestId('background-content').closest('[inert]')).toBeInTheDocument();
    const closeButton = within(dialog).getByRole('button', { name: /^(关闭|Close)$/ });
    expect(closeButton).toHaveFocus();

    fireEvent.click(closeButton);

    expect(screen.queryByRole('dialog', { name: '焦点弹窗' })).not.toBeInTheDocument();
    expect(screen.getByTestId('background-content').closest('[inert]')).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it('traps Tab within the active surface', () => {
    render(
      <UiLanguageProvider>
        <Modal isOpen onClose={vi.fn()} title="键盘弹窗">
          <button type="button">最后操作</button>
        </Modal>
      </UiLanguageProvider>,
    );

    const closeButton = within(screen.getByRole('dialog', { name: '键盘弹窗' }))
      .getByRole('button', { name: /^(关闭|Close)$/ });
    const lastButton = screen.getByRole('button', { name: '最后操作' });
    lastButton.focus();
    fireEvent.keyDown(lastButton, { key: 'Tab' });
    expect(closeButton).toHaveFocus();

    fireEvent.keyDown(closeButton, { key: 'Tab', shiftKey: true });
    expect(lastButton).toHaveFocus();
  });

  it('reactivates an underlying dialog before restoring stacked focus', () => {
    const Harness = () => {
      const [modalOpen, setModalOpen] = useState(false);
      const [confirmOpen, setConfirmOpen] = useState(false);
      return (
        <UiLanguageProvider>
          <button type="button" onClick={() => setModalOpen(true)}>打开外层</button>
          <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title="外层">
            <button type="button" onClick={() => setConfirmOpen(true)}>打开确认</button>
            <ConfirmDialog
              isOpen={confirmOpen}
              title="内层确认"
              message="继续吗？"
              onConfirm={vi.fn()}
              onCancel={() => setConfirmOpen(false)}
            />
          </Modal>
        </UiLanguageProvider>
      );
    };
    render(<Harness />);

    const outerTrigger = screen.getByRole('button', { name: '打开外层' });
    outerTrigger.focus();
    fireEvent.click(outerTrigger);
    const confirmTrigger = screen.getByRole('button', { name: '打开确认' });
    confirmTrigger.focus();
    fireEvent.click(confirmTrigger);

    const outerDialog = screen.getByText('外层').closest('[role="dialog"]');
    expect(outerDialog?.closest('[data-overlay-root="modal"]')).toHaveAttribute('inert');
    expect(screen.getByRole('dialog', { name: '内层确认' })).toBeInTheDocument();

    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: '内层确认' })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: '外层' })).toBeInTheDocument();
    expect(confirmTrigger).toHaveFocus();

    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: '外层' })).not.toBeInTheDocument();
    expect(outerTrigger).toHaveFocus();
  });

  it('blocks every dismissal path while a mutation is pending', () => {
    const onClose = vi.fn();
    const onDismissBlocked = vi.fn();
    render(
      <UiLanguageProvider>
        <Modal
          isOpen
          onClose={onClose}
          onDismissBlocked={onDismissBlocked}
          dismissDisabled
          dismissDisabledReason="正在保存，暂时无法关闭"
          title="保存设置"
        >
          内容
        </Modal>
      </UiLanguageProvider>,
    );

    expect(screen.getByRole('status')).toHaveTextContent('正在保存，暂时无法关闭');
    fireEvent.keyDown(document.body, { key: 'Escape' });
    fireEvent.click(within(screen.getByRole('dialog', { name: '保存设置' }))
      .getByRole('button', { name: /^(关闭|Close)$/ }));

    expect(onClose).not.toHaveBeenCalled();
    expect(onDismissBlocked).toHaveBeenCalledTimes(2);
  });
});
