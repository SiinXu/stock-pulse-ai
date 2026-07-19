import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TimePicker } from '../TimePicker';

describe('TimePicker', () => {
  it('commits the selected hour and minute after confirmation', () => {
    const onChange = vi.fn();
    render(<TimePicker value="09:20" onChange={onChange} ariaLabel="执行时间" />);

    fireEvent.click(screen.getByRole('button', { name: '执行时间' }));
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-hour="10"]')!);
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-minute="30"]')!);
    fireEvent.click(screen.getByRole('button', { name: '确定' }));

    expect(onChange).toHaveBeenCalledWith('10:30');
    expect(screen.queryByRole('dialog', { name: '执行时间' })).not.toBeInTheDocument();
  });

  it('opens automatically without committing a placeholder value', async () => {
    const onChange = vi.fn();
    render(<TimePicker value="" onChange={onChange} ariaLabel="新增时间" autoOpen />);

    expect(await screen.findByRole('dialog', { name: '新增时间' })).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });
});
