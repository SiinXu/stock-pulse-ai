import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ResponsiveFilterPanel } from '../ResponsiveFilterPanel';

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
  it('keeps the desktop form and exposes the mobile advanced-filter count', () => {
    const onApply = vi.fn();
    render(<Harness onApply={onApply} />);

    expect(screen.getByRole('button', { name: 'More filters (2)' })).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it('preserves controlled advanced values across drawer close and reopen', () => {
    const onApply = vi.fn();
    render(<Harness onApply={onApply} />);

    const trigger = screen.getByRole('button', { name: 'More filters (2)' });
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Advanced filters' });
    expect(screen.getAllByRole('textbox', { name: 'Status' })).toHaveLength(1);
    const drawerInput = within(dialog).getByRole('textbox', { name: 'Status' });
    fireEvent.change(drawerInput, { target: { value: 'closed' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /Close drawer|关闭抽屉/ }));

    fireEvent.click(trigger);
    const reopenedDialog = screen.getByRole('dialog', { name: 'Advanced filters' });
    expect(within(reopenedDialog).getByRole('textbox', { name: 'Status' })).toHaveValue('closed');
    fireEvent.click(within(reopenedDialog).getByRole('button', { name: 'Apply' }));

    expect(onApply).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog', { name: 'Advanced filters' })).not.toBeInTheDocument();
  });

  it('shares the disabled apply state between desktop and mobile controls', () => {
    render(<Harness applyDisabled />);

    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'More filters (2)' }));
    expect(within(screen.getByRole('dialog', { name: 'Advanced filters' })).getByRole('button', { name: 'Apply' })).toBeDisabled();
  });

  it('announces the loading label while applying', () => {
    render(<Harness isApplying />);

    expect(screen.getByRole('button', { name: 'Applying' })).toBeDisabled();
  });
});
