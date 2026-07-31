import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DatePicker } from '../DatePicker';

describe('DatePicker', () => {
  it('opens the shared calendar and commits a selected ISO date', () => {
    const onChange = vi.fn();
    const { container } = render(
      <DatePicker value="2026-07-18" onChange={onChange} ariaLabel="交易日期" />,
    );

    fireEvent.click(screen.getByRole('textbox', { name: '交易日期' }));
    expect(screen.getByRole('dialog', { name: '交易日期' })).toBeInTheDocument();

    const nextDate = document.querySelector<HTMLButtonElement>('[data-date="2026-07-20"]');
    expect(nextDate).not.toBeNull();
    fireEvent.click(nextDate!);

    expect(onChange).toHaveBeenCalledWith('2026-07-20');
    expect(screen.queryByRole('dialog', { name: '交易日期' })).not.toBeInTheDocument();
    expect(container.querySelector('[data-value="2026-07-18"]')).toBeInTheDocument();
  });

  it('disables dates outside the configured range', () => {
    render(
      <DatePicker
        value="2026-07-18"
        onChange={() => undefined}
        ariaLabel="日期"
        min="2026-07-10"
        max="2026-07-20"
      />,
    );

    fireEvent.click(screen.getByRole('textbox', { name: '日期' }));
    expect(document.querySelector('[data-date="2026-07-09"]')).toBeDisabled();
    expect(document.querySelector('[data-date="2026-07-20"]')).not.toBeDisabled();
  });

  it('keeps the date field picker-only and opens the calendar from the keyboard', () => {
    const onChange = vi.fn();
    render(<DatePicker value="2026-07-18" onChange={onChange} ariaLabel="日期" />);

    const input = screen.getByRole('textbox', { name: '日期' });
    expect(input).not.toHaveAttribute('readonly');
    expect(input).toHaveAttribute('aria-readonly', 'true');
    input.focus();

    expect(input).toHaveFocus();
    expect(screen.queryByRole('dialog', { name: '日期' })).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: '2026-07-19' } });
    expect(onChange).not.toHaveBeenCalled();
    expect(input).toHaveValue('2026-07-18');

    fireEvent.keyDown(input, { key: 'Enter' });
    expect(screen.getByRole('dialog', { name: '日期' })).toBeInTheDocument();
  });

  it('keeps native required and pattern validation active', () => {
    const { rerender } = render(
      <DatePicker value="" onChange={() => undefined} ariaLabel="交易日期" required />,
    );

    const input = screen.getByRole('textbox', { name: '交易日期' }) as HTMLInputElement;
    expect(input.willValidate).toBe(true);
    expect(input.validity.valueMissing).toBe(true);
    expect(input.checkValidity()).toBe(false);

    rerender(
      <DatePicker value="07/18/2026" onChange={() => undefined} ariaLabel="交易日期" required />,
    );
    expect(input.validity.patternMismatch).toBe(true);
    expect(input.checkValidity()).toBe(false);
  });

  it('clears only optional values without opening the calendar and returns focus to the field', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <DatePicker value="2026-07-18" onChange={onChange} ariaLabel="日期" />,
    );

    fireEvent.click(screen.getByRole('button', { name: '清除 日期' }));
    expect(onChange).toHaveBeenCalledWith('');
    expect(screen.queryByRole('dialog', { name: '日期' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '日期' })).toHaveFocus();

    rerender(
      <DatePicker value="2026-07-18" onChange={onChange} ariaLabel="日期" required />,
    );
    expect(screen.queryByRole('button', { name: '清除 日期' })).not.toBeInTheDocument();
  });

  it('does not open or expose a clear action while disabled', () => {
    render(
      <DatePicker value="2026-07-18" onChange={() => undefined} ariaLabel="日期" disabled />,
    );

    const input = screen.getByRole('textbox', { name: '日期' });
    expect(input).toBeDisabled();
    expect(screen.getByRole('button', { name: '打开 日期 日历' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '清除 日期' })).not.toBeInTheDocument();
    fireEvent.click(input.parentElement!);
    expect(screen.queryByRole('dialog', { name: '日期' })).not.toBeInTheDocument();
  });

  it('inherits disabled fieldset semantics across wrapper and portal interactions', async () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <fieldset>
        <DatePicker value="2026-07-18" onChange={onChange} ariaLabel="日期" />
      </fieldset>,
    );

    const input = screen.getByRole('textbox', { name: '日期' });
    fireEvent.click(input.parentElement!);
    expect(screen.getByRole('dialog', { name: '日期' })).toBeInTheDocument();

    rerender(
      <fieldset disabled>
        <DatePicker value="2026-07-18" onChange={onChange} ariaLabel="日期" />
      </fieldset>,
    );

    expect(input).toBeDisabled();
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: '日期' })).not.toBeInTheDocument();
    });

    fireEvent.click(input.parentElement!);

    expect(screen.queryByRole('dialog', { name: '日期' })).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('guards an open portal when its ancestor fieldset becomes disabled outside React', () => {
    const onChange = vi.fn();
    const { container } = render(
      <fieldset>
        <DatePicker value="2026-07-18" onChange={onChange} ariaLabel="日期" />
      </fieldset>,
    );

    fireEvent.click(screen.getByRole('textbox', { name: '日期' }).parentElement!);
    const day = document.querySelector<HTMLButtonElement>('[data-date="2026-07-20"]');
    expect(day).not.toBeNull();

    container.querySelector('fieldset')!.disabled = true;
    fireEvent.click(day!);

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog', { name: '日期' })).not.toBeInTheDocument();
  });

  it('applies compact geometry to both the trigger and calendar action', () => {
    render(
      <DatePicker
        value=""
        onChange={() => undefined}
        ariaLabel="日期"
        size="compact"
      />,
    );

    const input = screen.getByRole('textbox', { name: '日期' });
    const trigger = input.parentElement;
    const action = screen.getByRole('button', { name: '打开 日期 日历' });

    expect(trigger).toHaveAttribute('data-control', 'date-picker');
    expect(trigger).toHaveAttribute('data-size', 'compact');
    expect(trigger).toHaveClass('h-8', 'min-h-8', 'min-w-8');
    expect(trigger).not.toHaveClass('min-h-11');
    expect(action).toHaveClass('h-8', 'w-8');
    expect(action).not.toHaveClass('h-11', 'w-11');
  });
});
