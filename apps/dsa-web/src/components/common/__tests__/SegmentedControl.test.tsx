import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SegmentedControl } from '../SegmentedControl';
import { getTabId, getTabPanelId } from '../tabIds';

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

  it('uses stable shared IDs when controlling TabPanel content', () => {
    render(
      <SegmentedControl
        id="view-tabs"
        value="left"
        options={[
          { value: 'left', label: 'Left' },
          { value: 'right', label: 'Right' },
        ]}
        onChange={() => undefined}
        ariaLabel="View"
        getPanelId={(value) => getTabPanelId('view-tabs', value)}
      />,
    );

    expect(screen.getByRole('tablist', { name: 'View' })).toHaveAttribute('id', 'view-tabs');
    expect(screen.getByRole('tab', { name: 'Left' })).toHaveAttribute(
      'id',
      getTabId('view-tabs', 'left'),
    );
    expect(screen.getByRole('tab', { name: 'Left' })).toHaveAttribute(
      'aria-controls',
      getTabPanelId('view-tabs', 'left'),
    );
  });

  it('uses radio semantics for single-value modes without tab panels', () => {
    render(
      <SegmentedControl
        value="window"
        options={[
          { value: 'window', label: 'Window' },
          { value: 'one-day', label: 'One day' },
        ]}
        onChange={() => undefined}
        ariaLabel="Validation mode"
        getPanelId={(value) => `${value}-panel`}
        semantics="single-select"
      />,
    );

    expect(screen.getByRole('radiogroup', { name: 'Validation mode' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Window' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: 'Window' })).not.toHaveAttribute('aria-controls');
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
  });

  it('supports radio keyboard selection and skips disabled options', () => {
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
        ariaLabel="Validation mode"
        semantics="single-select"
      />,
    );

    const middle = screen.getByRole('radio', { name: 'Middle' });
    fireEvent.keyDown(middle, { key: 'ArrowRight' });
    expect(onChange).toHaveBeenLastCalledWith('last');

    fireEvent.keyDown(middle, { key: 'ArrowLeft' });
    expect(onChange).toHaveBeenLastCalledWith('first');

    fireEvent.keyDown(middle, { key: 'Home' });
    expect(onChange).toHaveBeenLastCalledWith('first');

    fireEvent.keyDown(middle, { key: 'End' });
    expect(onChange).toHaveBeenLastCalledWith('last');
  });
});
