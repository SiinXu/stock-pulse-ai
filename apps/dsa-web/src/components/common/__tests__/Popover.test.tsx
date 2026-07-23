import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { APP_ROUTE_PATHS } from '../../../routing/routes';
import { Modal } from '../Modal';
import { OVERLAY_Z } from '../overlayZ';
import { Popover } from '../Popover';
import { Select } from '../Select';
import { Tooltip } from '../Tooltip';

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

  it('positions a right-side flyout against the trigger without stealing hover focus', async () => {
    const rect = (left: number, top: number, width: number, height: number): DOMRect => ({
      bottom: top + height,
      height,
      left,
      right: left + width,
      top,
      width,
      x: left,
      y: top,
      toJSON: () => ({}),
    });
    const rectSpy = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockImplementation(function getBoundingClientRect(this: HTMLElement) {
        return this.getAttribute('role') === 'menu'
          ? rect(0, 0, 180, 100)
          : rect(20, 50, 44, 44);
      });
    try {
      render(
        <Popover
          defaultOpen
          placement="right"
          autoFocusContent={false}
          contentRole="menu"
          ariaLabel="Research"
          trigger={() => <button type="button">Research</button>}
        >
          <a href={APP_ROUTE_PATHS.researchMarket} role="menuitem">Market review</a>
        </Popover>,
      );

      const trigger = screen.getByRole('button', { name: 'Research' });
      trigger.focus();
      const menu = await screen.findByRole('menu', { name: 'Research' });
      await waitFor(() => {
        expect(menu.style.left).toBe('68px');
        expect(menu.style.top).toBe('50px');
        expect(menu.style.visibility).toBe('visible');
      });
      expect(trigger).toHaveFocus();
    } finally {
      rectSpy.mockRestore();
    }
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

  it('keeps a nested popup mounted while its option handles pointer selection', async () => {
    const onSelect = vi.fn();
    render(
      <Popover
        defaultOpen
        contentRole="menu"
        ariaLabel="Profile settings"
        trigger={() => <button type="button">Profile</button>}
      >
        <Popover
          defaultOpen
          contentRole="menu"
          ariaLabel="Language options"
          trigger={() => <button type="button">Language</button>}
        >
          <button type="button" role="menuitem" onClick={onSelect}>English</button>
        </Popover>
      </Popover>,
    );

    const outerMenu = await screen.findByRole('menu', { name: 'Profile settings' });
    const option = await screen.findByRole('menuitem', { name: 'English' });
    fireEvent.mouseDown(option);
    fireEvent.click(option);

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(outerMenu).toBeInTheDocument();
  });

  it('closes only the topmost popup on Escape', async () => {
    render(
      <Popover
        defaultOpen
        contentRole="menu"
        ariaLabel="Profile settings"
        trigger={() => <button type="button">Profile</button>}
      >
        <Popover
          defaultOpen
          contentRole="menu"
          ariaLabel="Language options"
          trigger={() => <button type="button">Language</button>}
        >
          <button type="button" role="menuitem">English</button>
        </Popover>
      </Popover>,
    );

    const outerMenu = await screen.findByRole('menu', { name: 'Profile settings' });
    const innerMenu = await screen.findByRole('menu', { name: 'Language options' });

    fireEvent.keyDown(innerMenu, { key: 'Escape' });

    expect(screen.queryByRole('menu', { name: 'Language options' })).not.toBeInTheDocument();
    expect(outerMenu).toBeInTheDocument();
  });

  it('keeps the parent menu open when a nested Select consumes Escape', async () => {
    const onSelect = vi.fn();
    render(
      <UiLanguageProvider>
        <Popover
          defaultOpen
          contentRole="menu"
          ariaLabel="Profile settings"
          trigger={() => <button type="button">Profile</button>}
        >
          <Select
            value="en"
            onChange={onSelect}
            options={[
              { value: 'en', label: 'English' },
              { value: 'zh', label: 'Chinese' },
            ]}
            ariaLabel="Language"
          />
        </Popover>
      </UiLanguageProvider>,
    );

    const outerMenu = await screen.findByRole('menu', { name: 'Profile settings' });
    const selectTrigger = screen.getByRole('combobox', { name: 'Language' });
    fireEvent.click(selectTrigger);
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    fireEvent.keyDown(selectTrigger, { key: 'Escape' });

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(outerMenu).toBeInTheDocument();

    fireEvent.click(selectTrigger);
    const option = screen.getByRole('option', { name: 'Chinese' });
    fireEvent.mouseDown(option);
    fireEvent.click(option);
    expect(onSelect).toHaveBeenCalledWith('zh');
    expect(outerMenu).toBeInTheDocument();
  });

  it('lets a higher Tooltip consume Escape before an unrelated Popover', async () => {
    render(
      <>
        <Popover
          defaultOpen
          contentRole="menu"
          ariaLabel="Profile settings"
          trigger={() => <button type="button">Profile</button>}
        >
          <button type="button" role="menuitem">Account</button>
        </Popover>
        <Tooltip content="External guidance">
          <button type="button">External help</button>
        </Tooltip>
      </>,
    );

    const outerMenu = await screen.findByRole('menu', { name: 'Profile settings' });
    const menuItem = screen.getByRole('menuitem', { name: 'Account' });
    const helpTrigger = screen.getByRole('button', { name: 'External help' });
    fireEvent.mouseEnter(helpTrigger.parentElement as HTMLElement);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();

    fireEvent.keyDown(menuItem, { key: 'Escape' });

    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    expect(outerMenu).toBeInTheDocument();
  });

  it('dismisses on a pointer press inside an unrelated Tooltip trigger', async () => {
    render(
      <>
        <Popover
          defaultOpen
          contentRole="menu"
          ariaLabel="Profile settings"
          trigger={() => <button type="button">Profile</button>}
        >
          <button type="button" role="menuitem">Account</button>
        </Popover>
        <Tooltip content="External guidance">
          <button type="button">External help</button>
        </Tooltip>
      </>,
    );

    await screen.findByRole('menu', { name: 'Profile settings' });
    const helpTrigger = screen.getByRole('button', { name: 'External help' });
    fireEvent.mouseEnter(helpTrigger.parentElement as HTMLElement);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();

    fireEvent.mouseDown(helpTrigger);

    expect(screen.queryByRole('menu', { name: 'Profile settings' })).not.toBeInTheDocument();
  });

  it('keeps ancestor menus open when an owned nested popup contains a Tooltip trigger', async () => {
    render(
      <Popover
        defaultOpen
        contentRole="menu"
        ariaLabel="Profile settings"
        trigger={() => <button type="button">Profile</button>}
      >
        <Popover
          defaultOpen
          contentRole="menu"
          ariaLabel="Language options"
          trigger={() => <button type="button">Language</button>}
        >
          <Tooltip content="Language guidance">
            <button type="button" role="menuitem">Language help</button>
          </Tooltip>
        </Popover>
      </Popover>,
    );

    const outerMenu = await screen.findByRole('menu', { name: 'Profile settings' });
    const innerMenu = await screen.findByRole('menu', { name: 'Language options' });
    const helpTrigger = screen.getByRole('menuitem', { name: 'Language help' });
    fireEvent.mouseEnter(helpTrigger.parentElement as HTMLElement);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();

    fireEvent.mouseDown(helpTrigger);

    expect(outerMenu).toBeInTheDocument();
    expect(innerMenu).toBeInTheDocument();
  });
});
