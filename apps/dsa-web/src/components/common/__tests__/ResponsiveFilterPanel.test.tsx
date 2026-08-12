import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ResponsiveFilterPanel } from '../ResponsiveFilterPanel';

function setMobileViewport(isMobile: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: isMobile && query.includes('max-width'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

function Harness({
  onApply = () => undefined,
  applyDisabled = false,
  isApplying = false,
}: {
  onApply?: () => void;
  applyDisabled?: boolean;
  isApplying?: boolean;
}) {
  const [advancedValue, setAdvancedValue] = useState('active');
  return (
    <UiLanguageProvider>
      <ResponsiveFilterPanel
        filterLabel="More filters"
        drawerTitle="Advanced filters"
        applyLabel="Apply"
        applyDisabled={applyDisabled}
        isApplying={isApplying}
        loadingLabel="Applying"
        activeCount={2}
        onApply={onApply}
        basic={<input aria-label="Market" defaultValue="US" />}
        advanced={(
          <input
            aria-label="Status"
            value={advancedValue}
            onChange={(event) => setAdvancedValue(event.target.value)}
          />
        )}
      />
    </UiLanguageProvider>
  );
}

describe('ResponsiveFilterPanel', () => {
  beforeEach(() => {
    // Default setupTests matchMedia always returns matches:false → desktop layout.
    setMobileViewport(false);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('submits the desktop form and keeps basic filters inline on large viewports', () => {
    const onApply = vi.fn();
    render(<Harness onApply={onApply} />);

    expect(screen.getByRole('textbox', { name: 'Market' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'More filters (2)' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it('collapses basic filters behind a single Filters control on narrow viewports (#879 B2)', () => {
    setMobileViewport(true);
    render(<Harness />);

    expect(screen.queryByRole('textbox', { name: 'Market' })).not.toBeInTheDocument();
    const trigger = screen.getByRole('button', { name: 'More filters (2)' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Advanced filters' });
    expect(within(dialog).getByRole('textbox', { name: 'Market' })).toBeInTheDocument();
    expect(within(dialog).getByRole('textbox', { name: 'Status' })).toBeInTheDocument();
  });

  it('preserves controlled advanced values across drawer close and reopen', () => {
    setMobileViewport(true);
    const onApply = vi.fn();
    render(<Harness onApply={onApply} />);

    const trigger = screen.getByRole('button', { name: 'More filters (2)' });
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Advanced filters' });
    const drawerInput = within(dialog).getByRole('textbox', { name: 'Status' });
    fireEvent.change(drawerInput, { target: { value: 'closed' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close drawer' }));

    fireEvent.click(trigger);
    const reopenedDialog = screen.getByRole('dialog', { name: 'Advanced filters' });
    expect(within(reopenedDialog).getByRole('textbox', { name: 'Status' })).toHaveValue('closed');
    fireEvent.click(within(reopenedDialog).getByRole('button', { name: 'Apply' }));

    expect(onApply).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog', { name: 'Advanced filters' })).not.toBeInTheDocument();
  });

  it('shares disabled and loading state between desktop and mobile actions', () => {
    const desktop = render(<Harness applyDisabled />);
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
    desktop.unmount();

    setMobileViewport(true);
    const mobile = render(<Harness applyDisabled />);
    fireEvent.click(screen.getByRole('button', { name: 'More filters (2)' }));
    expect(within(screen.getByRole('dialog', { name: 'Advanced filters' })).getByRole('button', { name: 'Apply' })).toBeDisabled();
    mobile.unmount();

    setMobileViewport(false);
    render(<Harness isApplying />);
    expect(screen.getByRole('button', { name: 'Apply' })).toHaveAttribute('aria-busy', 'true');
  });
});
