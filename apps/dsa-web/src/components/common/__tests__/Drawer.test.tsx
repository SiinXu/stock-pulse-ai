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
        <Drawer isOpen onClose={() => undefined} title="History">
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
});
