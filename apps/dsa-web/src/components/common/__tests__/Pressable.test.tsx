import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Pressable } from '../Pressable';

describe('Pressable', () => {
  it('provides a safe default type, ref, focus treatment, and touch target', () => {
    const onClick = vi.fn();
    const ref = createRef<HTMLButtonElement>();
    render(<Pressable ref={ref} onClick={onClick}>Open row</Pressable>);

    const button = screen.getByRole('button', { name: 'Open row' });
    expect(button).toHaveAttribute('type', 'button');
    expect(button).toHaveClass('min-h-6', 'min-w-6', 'focus-visible:ring-2');
    expect(ref.current).toBe(button);
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
