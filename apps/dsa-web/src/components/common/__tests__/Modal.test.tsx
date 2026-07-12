import { fireEvent, render, screen } from '@testing-library/react';
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
});
