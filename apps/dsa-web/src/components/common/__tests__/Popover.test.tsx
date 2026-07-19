import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { Modal } from '../Modal';
import { OVERLAY_Z } from '../overlayZ';
import { Popover } from '../Popover';

describe('Popover', () => {
  it('opens from its trigger and closes on outside press', () => {
    render(
      <Popover
        contentRole="menu"
        ariaLabel="操作"
        trigger={({ open, toggle }) => (
          <button type="button" aria-expanded={open} onClick={toggle}>打开</button>
        )}
      >
        <button type="button" role="menuitem">项目</button>
      </Popover>,
    );

    fireEvent.click(screen.getByRole('button', { name: '打开' }));
    expect(screen.getByRole('menu', { name: '操作' })).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('menu', { name: '操作' })).not.toBeInTheDocument();
  });

  it('supports controlled state and Escape closing', () => {
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <Popover
        open
        onOpenChange={onOpenChange}
        trigger={() => <button type="button">打开</button>}
      >
        内容
      </Popover>,
    );

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onOpenChange).toHaveBeenCalledWith(false);

    rerender(
      <Popover open={false} trigger={() => <button type="button">打开</button>}>
        内容
      </Popover>,
    );
    expect(screen.queryByText('内容')).not.toBeInTheDocument();
  });

  it('portals into a parent dialog and consumes Escape before the dialog', async () => {
    const onModalClose = vi.fn();
    render(
      <UiLanguageProvider>
        <Modal isOpen title="Edit filters" onClose={onModalClose}>
          <Popover
            defaultOpen
            contentRole="menu"
            ariaLabel="Filter actions"
            trigger={({ open, toggle }) => (
              <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={toggle}>
                Actions
              </button>
            )}
          >
            <button type="button" role="menuitem">Reset filter</button>
          </Popover>
        </Modal>
      </UiLanguageProvider>,
    );

    const dialog = screen.getByRole('dialog', { name: 'Edit filters' });
    const trigger = screen.getByRole('button', { name: 'Actions' });
    const menu = screen.getByRole('menu', { name: 'Filter actions' });
    expect(dialog).toContainElement(menu);
    expect(trigger.parentElement).not.toContainElement(menu);
    expect(menu).toHaveAttribute('data-dialog-popup', 'true');
    expect(menu.style.zIndex).toBe(String(OVERLAY_Z.popover));

    fireEvent.keyDown(menu, { key: 'Escape' });

    expect(screen.queryByRole('menu', { name: 'Filter actions' })).not.toBeInTheDocument();
    expect(onModalClose).not.toHaveBeenCalled();
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});
