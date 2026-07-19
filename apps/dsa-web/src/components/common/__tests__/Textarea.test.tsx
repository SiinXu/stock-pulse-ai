import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Textarea } from '../Textarea';

describe('Textarea', () => {
  it('associates its label and hint with the native textarea', () => {
    render(<Textarea name="notes" label="Notes" hint="Optional context" />);

    const textarea = screen.getByRole('textbox', { name: 'Notes' });
    expect(textarea).toHaveAttribute('id', 'notes');
    expect(textarea).toHaveAttribute('aria-describedby', 'notes-hint');
  });

  it('forwards its ref and exposes errors through aria', () => {
    const ref = { current: null as HTMLTextAreaElement | null };
    render(<Textarea ref={ref} name="reason" label="Reason" error="Required" />);

    const textarea = screen.getByRole('textbox', { name: 'Reason' });
    expect(ref.current).toBe(textarea);
    expect(textarea).toHaveAttribute('aria-invalid', 'true');
    expect(textarea).toHaveAttribute('aria-describedby', 'reason-error');
    expect(screen.getByRole('alert')).toHaveTextContent('Required');
  });
});
