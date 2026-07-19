import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SegmentedControl } from '../SegmentedControl';

describe('SegmentedControl', () => {
  it('marks and changes the active tab', () => {
    const onChange = vi.fn();
    render(
      <SegmentedControl
        value="left"
        options={[
          { value: 'left', label: 'Left' },
          { value: 'right', label: 'Right' },
        ]}
        onChange={onChange}
        ariaLabel="View"
      />,
    );

    expect(screen.getByRole('tab', { name: 'Left' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Left' })).toHaveClass('segmented-control-tab', 'min-h-6');
    fireEvent.click(screen.getByRole('tab', { name: 'Right' }));
    expect(onChange).toHaveBeenCalledWith('right');
  });

  it('supports arrow, Home, and End navigation while skipping disabled tabs', () => {
    const onChange = vi.fn();
    render(
      <SegmentedControl
        value="middle"
        options={[
          { value: 'first', label: 'First' },
          { value: 'middle', label: 'Middle' },
          { value: 'disabled', label: 'Disabled', disabled: true },
          { value: 'last', label: 'Last' },
        ]}
        onChange={onChange}
        ariaLabel="View"
      />,
    );

    const middle = screen.getByRole('tab', { name: 'Middle' });
    fireEvent.keyDown(middle, { key: 'ArrowRight' });
    expect(onChange).toHaveBeenLastCalledWith('last');

    fireEvent.keyDown(middle, { key: 'Home' });
    expect(onChange).toHaveBeenLastCalledWith('first');

    fireEvent.keyDown(middle, { key: 'End' });
    expect(onChange).toHaveBeenLastCalledWith('last');
  });
});
