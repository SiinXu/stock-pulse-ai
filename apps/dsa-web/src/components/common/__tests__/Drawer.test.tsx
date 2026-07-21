// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { Drawer } from '../Drawer';

describe('Drawer overlay behavior', () => {
  it('restores pre-existing document state when an open drawer unmounts', () => {
    document.body.style.overflow = 'clip';
    const { container, unmount } = render(
      <UiLanguageProvider>
        <Drawer isOpen onClose={() => undefined} title="History" variant="detail">
          <p>Reports</p>
        </Drawer>
      </UiLanguageProvider>,
    );

    expect(container).toHaveAttribute('inert');
    expect(document.body.style.overflow).toBe('hidden');

    unmount();

    expect(container).not.toHaveAttribute('inert');
    expect(container).not.toHaveAttribute('aria-hidden');
    expect(document.body.style.overflow).toBe('clip');
    document.body.style.overflow = '';
  });

  it('portals outside the application, isolates the background, and restores focus', () => {
    const Harness = () => {
      const [isOpen, setIsOpen] = useState(false);
      return (
        <UiLanguageProvider>
          <button type="button" onClick={() => setIsOpen(true)}>Open history</button>
          <Drawer
            isOpen={isOpen}
            onClose={() => setIsOpen(false)}
            title="History"
            description="Recent reports"
            variant="detail"
          >
            <button type="button">Choose report</button>
          </Drawer>
        </UiLanguageProvider>
      );
    };

    const { container } = render(<Harness />);
    const trigger = screen.getByRole('button', { name: 'Open history' });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole('dialog', { name: 'History' });
    expect(dialog).toHaveAccessibleDescription('Recent reports');
    expect(container).toHaveAttribute('inert');
    expect(container).not.toContainElement(dialog);
    expect(dialog.closest('[data-overlay-root="drawer"]')).toBeInTheDocument();
    expect(dialog).toContainElement(document.activeElement as HTMLElement);

    fireEvent.keyDown(dialog, { key: 'Escape' });

    expect(screen.queryByRole('dialog', { name: 'History' })).not.toBeInTheDocument();
    expect(container).not.toHaveAttribute('inert');
    expect(trigger).toHaveFocus();
  });

  it('derives side and width from semantic navigation and detail variants', () => {
    const { rerender } = render(
      <UiLanguageProvider>
        <Drawer isOpen onClose={() => undefined} title="Navigation" variant="navigation">
          <p>Routes</p>
        </Drawer>
      </UiLanguageProvider>,
    );

    let dialog = screen.getByRole('dialog', { name: 'Navigation' });
    expect(dialog).toHaveAttribute('data-drawer-variant', 'navigation');
    expect(dialog).toHaveAttribute('data-drawer-side', 'left');
    expect(dialog.parentElement).toHaveClass('max-w-xs');

    rerender(
      <UiLanguageProvider>
        <Drawer isOpen onClose={() => undefined} title="Details" variant="detail" size="wide">
          <p>Details</p>
        </Drawer>
      </UiLanguageProvider>,
    );

    dialog = screen.getByRole('dialog', { name: 'Details' });
    expect(dialog).toHaveAttribute('data-drawer-variant', 'detail');
    expect(dialog).toHaveAttribute('data-drawer-side', 'right');
    expect(dialog).toHaveAttribute('data-drawer-size', 'wide');
    expect(dialog.parentElement).toHaveClass('max-w-[40rem]');
  });
});
