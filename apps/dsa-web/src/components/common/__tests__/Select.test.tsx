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
    expect(screen.getByRole('listbox', { name: '服务商' })).toBeInTheDocument();
    const option = screen.getByRole('option', { name: 'OpenAI' });
    expect(option).toHaveClass('min-h-9');
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

  it('forwards its trigger ref and matches the popup width by default', () => {
    const ref = { current: null as HTMLButtonElement | null };
    const rectSpy = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function mockRect(this: HTMLElement) {
      if (this.getAttribute('role') === 'combobox') {
        return new DOMRect(24, 40, 240, 36);
      }
      return new DOMRect(0, 0, 320, 100);
    });
    render(
      <Select
        ref={ref}
        width="full"
        value="one"
        onChange={() => {}}
        options={[{ value: 'one', label: 'One' }]}
        ariaLabel="Full-width select"
      />,
    );

    const trigger = screen.getByRole('combobox', { name: 'Full-width select' });
    expect(ref.current).toBe(trigger);
    expect(trigger.closest('.flex-col')).toHaveClass('w-full');
    fireEvent.click(trigger);
    expect(screen.getByRole('listbox')).toHaveStyle({ width: '240px' });
    rectSpy.mockRestore();
  });

  it('supports typeahead without committing until the user confirms', () => {
    const onChange = vi.fn();
    render(
      <Select
        value="alpha"
        onChange={onChange}
        options={[
          { value: 'alpha', label: 'Alpha' },
          { value: 'beta', label: 'Beta' },
          { value: 'gamma', label: 'Gamma' },
        ]}
        ariaLabel="Typeahead select"
      />,
    );

    const trigger = screen.getByRole('combobox', { name: 'Typeahead select' });
    fireEvent.keyDown(trigger, { key: 'g' });
    expect(trigger).toHaveAttribute('aria-activedescendant', expect.stringContaining('option-2'));
    expect(onChange).not.toHaveBeenCalled();

    fireEvent.keyDown(trigger, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith('gamma');
  });

  it('keeps Space as the standard combobox open key', () => {
    render(
      <Select
        value="one"
        onChange={() => {}}
        options={[{ value: 'one', label: 'One' }]}
        ariaLabel="Space select"
      />,
    );

    const trigger = screen.getByRole('combobox', { name: 'Space select' });
    fireEvent.keyDown(trigger, { key: ' ' });
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });
});
