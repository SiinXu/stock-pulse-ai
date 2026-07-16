import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Select } from '../Select';

if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

describe('Select', () => {
  it('associates validation errors with the combobox trigger', () => {
    render(
      <>
        <Select
          value=""
          onChange={() => {}}
          options={[{ value: 'openai', label: 'OpenAI' }]}
          ariaLabel="服务商"
          ariaDescribedBy="provider-error"
          error
        />
        <p id="provider-error">请选择服务商</p>
      </>,
    );

    const trigger = screen.getByRole('combobox', { name: '服务商' });
    expect(trigger).toHaveAttribute('aria-invalid', 'true');
    expect(trigger).toHaveAttribute('aria-describedby', 'provider-error');
    expect(trigger).toHaveClass('min-h-11');
    expect(trigger).not.toHaveClass('sm:min-h-0');

    fireEvent.click(trigger);
    const option = screen.getByRole('option', { name: 'OpenAI' });
    expect(option).toHaveClass('min-h-11');
    expect(option).not.toHaveClass('sm:min-h-0');
  });
});
