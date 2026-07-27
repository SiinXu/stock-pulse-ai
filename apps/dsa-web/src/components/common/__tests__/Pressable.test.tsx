import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Pressable } from '../Pressable';

describe('Pressable', () => {
  it('provides the shared control, focus, and coarse-pointer hit-target contract', () => {
    const onClick = vi.fn();
    const ref = createRef<HTMLButtonElement>();

    render(
      <Pressable ref={ref} onClick={onClick} className="session-item">
        Open row
      </Pressable>,
    );

    const button = screen.getByRole('button', { name: 'Open row' });
    expect(ref.current).toBe(button);
    expect(button).toHaveAttribute('type', 'button');
    expect(button).toHaveAttribute('data-control', 'pressable');
    expect(button).toHaveClass(
      'control-hit-target',
      'focus-visible:ring-2',
      'focus-visible:ring-primary/25',
      'session-item',
    );

    button.focus();
    expect(button).toHaveFocus();
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('preserves native button attributes and blocks disabled interactions', () => {
    const onClick = vi.fn();

    render(
      <Pressable type="submit" disabled onClick={onClick}>
        Submit row
      </Pressable>,
    );

    const button = screen.getByRole('button', { name: 'Submit row' });
    expect(button).toHaveAttribute('type', 'submit');
    expect(button).toBeDisabled();
    expect(button).toHaveClass(
      'disabled:pointer-events-none',
      'disabled:cursor-not-allowed',
      'disabled:opacity-50',
    );

    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });
});
