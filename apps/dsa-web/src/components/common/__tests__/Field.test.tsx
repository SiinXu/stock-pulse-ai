import { createRef } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Field } from '../Field';

describe('Field', () => {
  it('forwards its wrapper ref and associates the label with its control', () => {
    const ref = createRef<HTMLDivElement>();

    render(
      <Field ref={ref} controlId="provider-key" label="Provider key" hint="Stored securely">
        <input id="provider-key" />
      </Field>,
    );

    expect(ref.current).toBeInstanceOf(HTMLDivElement);
    expect(screen.getByLabelText('Provider key')).toBeInTheDocument();
    expect(screen.getByText('Stored securely')).toBeInTheDocument();
  });
});
