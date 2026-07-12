import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
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
});
