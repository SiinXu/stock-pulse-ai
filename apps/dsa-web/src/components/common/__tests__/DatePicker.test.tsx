import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DatePicker } from '../DatePicker';

describe('DatePicker', () => {
  it('opens the shared calendar and commits a selected ISO date', () => {
    const onChange = vi.fn();
    const { container } = render(
      <DatePicker value="2026-07-18" onChange={onChange} ariaLabel="交易日期" />,
    );

    fireEvent.click(screen.getByRole('button', { name: '打开 交易日期 日历' }));
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

    fireEvent.click(screen.getByRole('button', { name: '打开 日期 日历' }));
    expect(document.querySelector('[data-date="2026-07-09"]')).toBeDisabled();
    expect(document.querySelector('[data-date="2026-07-20"]')).not.toBeDisabled();
  });

  it('keeps focus in the editable input instead of opening the calendar on focus', () => {
    render(<DatePicker value="2026-07-18" onChange={() => undefined} ariaLabel="日期" />);

    const input = screen.getByRole('textbox', { name: '日期' });
    input.focus();

    expect(input).toHaveFocus();
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
