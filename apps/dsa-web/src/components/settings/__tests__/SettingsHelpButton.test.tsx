import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { Modal } from '../../common/Modal';
import { SettingsHelpButton } from '../SettingsHelpButton';

function HelpHarness({ stacked = false }: { stacked?: boolean }) {
  const [outerOpen, setOuterOpen] = useState(stacked);

  const helpButton = (
    <SettingsHelpButton
      fieldKey="STOCK_LIST"
      title="Watchlist"
      helpKey="settings.base.STOCK_LIST"
    />
  );

  return (
    <UiLanguageProvider>
      {stacked ? (
        <Modal isOpen={outerOpen} onClose={() => setOuterOpen(false)} title="Outer settings dialog">
          {helpButton}
        </Modal>
      ) : (
        helpButton
      )}
    </UiLanguageProvider>
  );
}

describe('SettingsHelpButton overlay contract', () => {
  it('uses the shared modal root, isolates the page, and restores trigger focus', () => {
    const { container } = render(<HelpHarness />);
    const trigger = screen.getByRole('button', { name: /Watchlist/ });
    trigger.focus();
    fireEvent.click(trigger);

    const helpDialog = screen.getByRole('dialog', { name: 'Watchlist' });
    expect(helpDialog.closest('[data-overlay-root="modal"]')).toBeInTheDocument();
    expect(container).toHaveAttribute('inert');
    expect(document.body).toHaveStyle({ overflow: 'hidden' });
    expect(helpDialog).toContainElement(document.activeElement as HTMLElement);

    fireEvent.click(within(helpDialog).getByRole('button', { name: /Close/ }));

    expect(screen.queryByRole('dialog', { name: 'Watchlist' })).not.toBeInTheDocument();
    expect(container).not.toHaveAttribute('inert');
    expect(document.body).not.toHaveStyle({ overflow: 'hidden' });
    expect(trigger).toHaveFocus();
  });

  it('closes only Help on Escape while the underlying modal stays isolated and locked', () => {
    render(<HelpHarness stacked />);
    const outerDialog = screen.getByRole('dialog', { name: 'Outer settings dialog' });
    const trigger = within(outerDialog).getByRole('button', { name: /Watchlist/ });
    trigger.focus();
    fireEvent.click(trigger);

    const helpDialog = screen.getByRole('dialog', { name: 'Watchlist' });
    expect(outerDialog.closest('[data-overlay-root]')).toHaveAttribute('inert');
    expect(outerDialog.closest('[data-overlay-root]')).toHaveAttribute('aria-hidden', 'true');

    fireEvent.keyDown(helpDialog, { key: 'Escape' });

    expect(screen.queryByRole('dialog', { name: 'Watchlist' })).not.toBeInTheDocument();
    const remainingDialog = screen.getByRole('dialog', { name: 'Outer settings dialog' });
    expect(remainingDialog.closest('[data-overlay-root]')).not.toHaveAttribute('inert');
    expect(document.body).toHaveStyle({ overflow: 'hidden' });
    expect(trigger).toHaveFocus();
  });
});
