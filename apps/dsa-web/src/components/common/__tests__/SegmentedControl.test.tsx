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
});
