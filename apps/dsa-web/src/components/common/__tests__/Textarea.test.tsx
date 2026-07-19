import { createRef } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Textarea } from '../Textarea';

describe('Textarea', () => {
  it('forwards its native ref and connects field guidance to the control', () => {
    const ref = createRef<HTMLTextAreaElement>();

    render(
      <Textarea
        ref={ref}
        name="research-notes"
        label="Research notes"
        hint="Summarize the key evidence"
      />,
    );

    const textarea = screen.getByRole('textbox', { name: 'Research notes' });
    expect(ref.current).toBe(textarea);
    expect(textarea).toHaveAttribute('aria-describedby', 'research-notes-hint');
    expect(textarea).toHaveAttribute('data-size', 'comfortable');
    expect(screen.getByText('Summarize the key evidence')).toBeInTheDocument();
  });
});
