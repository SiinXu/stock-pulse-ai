import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Tooltip } from '../Tooltip';

describe('Tooltip', () => {
  it('stays dismissed after Escape until the active pointer and focus interactions end', () => {
    render(
      <Tooltip content="Details">
        <button type="button">Help</button>
      </Tooltip>,
    );

    const trigger = screen.getByRole('button', { name: 'Help' });
    const wrapper = trigger.parentElement!;
    fireEvent.mouseEnter(wrapper);
    fireEvent.focus(trigger);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();

    fireEvent.keyDown(trigger, { key: 'Escape' });
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    fireEvent.mouseEnter(wrapper);
    fireEvent.focus(trigger);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    fireEvent.blur(trigger);
    fireEvent.mouseLeave(wrapper);
    fireEvent.focus(trigger);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();
  });
});
