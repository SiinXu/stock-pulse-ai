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
    expect(trigger).toHaveAttribute('aria-describedby', screen.getByRole('tooltip').id);

    fireEvent.keyDown(trigger, { key: 'Escape' });
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    expect(trigger).not.toHaveAttribute('aria-describedby');

    fireEvent.mouseEnter(wrapper);
    fireEvent.focus(trigger);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    fireEvent.blur(trigger);
    fireEvent.mouseLeave(wrapper);
    fireEvent.focus(trigger);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();
  });

  it('preserves an existing description on the focused trigger', () => {
    render(
      <Tooltip content="Details">
        <button type="button" aria-describedby="existing-description">Help</button>
      </Tooltip>,
    );

    const trigger = screen.getByRole('button', { name: 'Help' });
    fireEvent.focus(trigger);
    const tooltip = screen.getByRole('tooltip');
    expect(trigger).toHaveAttribute('aria-describedby', `existing-description ${tooltip.id}`);

    fireEvent.blur(trigger);
    expect(trigger).toHaveAttribute('aria-describedby', 'existing-description');
  });
});
