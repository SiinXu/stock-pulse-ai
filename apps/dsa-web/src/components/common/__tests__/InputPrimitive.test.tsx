import { createRef } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { InputPrimitive } from '../InputPrimitive';

describe('InputPrimitive', () => {
  it('forwards native input props, invalid state, and refs', () => {
    const ref = createRef<HTMLInputElement>();
    render(<InputPrimitive ref={ref} aria-label="Symbol" name="symbol" autoComplete="off" invalid />);

    const input = screen.getByRole('textbox', { name: 'Symbol' });
    expect(input).toHaveAttribute('name', 'symbol');
    expect(input).toHaveAttribute('autocomplete', 'off');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(ref.current).toBe(input);
  });
});
