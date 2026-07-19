import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
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

  it('closes only the topmost nested popover on Escape', () => {
    render(
      <Popover
        contentRole="dialog"
        ariaLabel="Profile"
        trigger={({ toggle }) => <button type="button" onClick={toggle}>Open profile</button>}
      >
        <Popover
          contentRole="menu"
          ariaLabel="Theme"
          trigger={({ toggle }) => <button type="button" onClick={toggle}>Open theme</button>}
        >
          <button type="button" role="menuitem">Dark</button>
        </Popover>
      </Popover>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Open profile' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open theme' }));
    expect(screen.getByRole('menu', { name: 'Theme' })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu', { name: 'Theme' })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Profile' })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Profile' })).not.toBeInTheDocument();
  });
});
