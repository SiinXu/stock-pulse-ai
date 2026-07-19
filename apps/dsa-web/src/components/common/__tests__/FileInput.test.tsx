import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FileInput } from '../FileInput';

describe('FileInput', () => {
  it('forwards its ref and preserves native file attributes', () => {
    const ref = { current: null as HTMLInputElement | null };
    const onChange = vi.fn();
    render(
      <FileInput
        ref={ref}
        aria-label="Import configuration"
        accept=".env,.txt"
        onChange={onChange}
      />,
    );

    const input = screen.getByLabelText('Import configuration');
    expect(ref.current).toBe(input);
    expect(input).toHaveAttribute('type', 'file');
    expect(input).toHaveAttribute('accept', '.env,.txt');
    expect(input).toHaveClass('hidden');

    fireEvent.change(input);
    expect(onChange).toHaveBeenCalledOnce();
  });
});
