// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
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
    expect(trigger).toHaveClass('min-h-9');
    expect(trigger).not.toHaveClass('sm:min-h-0');

    fireEvent.click(trigger);
    const option = screen.getByRole('option', { name: 'OpenAI' });
    expect(option).toHaveClass('min-h-11');
    expect(option).not.toHaveClass('sm:min-h-0');
  });

  it('can place the shared listbox above a bottom-edge trigger', () => {
    const rectSpy = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function mockRect(this: HTMLElement) {
      if (this.getAttribute('role') === 'combobox') {
        return new DOMRect(100, 724, 160, 36);
      }
      return new DOMRect(0, 0, 200, 100);
    });
    render(
      <Select
        value="zh"
        onChange={() => {}}
        options={[
          { value: 'zh', label: '简体中文' },
          { value: 'en', label: 'English' },
        ]}
        ariaLabel="界面语言"
      />,
    );

    fireEvent.click(screen.getByRole('combobox', { name: '界面语言' }));

    expect(screen.getByRole('listbox')).toHaveStyle({ top: '620px' });
    rectSpy.mockRestore();
  });

  it('accepts shared trigger styling without styling the listbox wrapper', () => {
    render(
      <Select
        value="one"
        onChange={() => {}}
        options={[{ value: 'one', label: 'One' }]}
        ariaLabel="Styled select"
        triggerClassName="min-h-11 rounded-md"
      />,
    );

    expect(screen.getByRole('combobox', { name: 'Styled select' })).toHaveClass('min-h-11', 'rounded-md');
  });
});
