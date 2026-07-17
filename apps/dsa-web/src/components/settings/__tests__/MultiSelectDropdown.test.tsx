import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MultiSelectDropdown } from '../MultiSelectDropdown';

const options = [
  { value: 'a', label: 'Alpha' },
  { value: 'b', label: 'Beta' },
  { value: 'c', label: 'Gamma' },
];

describe('MultiSelectDropdown', () => {
  it('keeps options collapsed behind a trigger and serializes toggles in catalog order', () => {
    const onChange = vi.fn();
    render(<MultiSelectDropdown options={options} selected={['c']} onChange={onChange} />);

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    const trigger = screen.getByRole('button', { name: /已选/ });
    expect(trigger).toHaveTextContent('已选 1 / 3');
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');

    fireEvent.click(trigger);
    const listbox = screen.getByRole('listbox');
    const checkboxes = within(listbox).getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(3);
    // Below the threshold the popup has no search box.
    expect(screen.queryByLabelText('搜索选项')).not.toBeInTheDocument();

    // Selecting a serializes in catalog order, not click order.
    fireEvent.click(checkboxes[0]);
    expect(onChange).toHaveBeenCalledWith(['a', 'c']);
  });

  it('keeps unknown selected values visible, counted, and removable', () => {
    const onChange = vi.fn();
    render(<MultiSelectDropdown options={options} selected={['b', 'mystery']} onChange={onChange} />);

    expect(screen.getByRole('button', { name: /已选/ })).toHaveTextContent('已选 2 / 4');
    expect(screen.getByText('mystery')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '移除 mystery' }));
    expect(onChange).toHaveBeenCalledWith(['b']);
  });

  it('appends picks in selection order and shows priority positions when ordered', () => {
    const onChange = vi.fn();
    render(<MultiSelectDropdown options={options} selected={['c', 'a']} onChange={onChange} ordered />);

    // Chips carry priority positions in ordered mode.
    expect(screen.getByText('1. Gamma')).toBeInTheDocument();
    expect(screen.getByText('2. Alpha')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /已选/ }));
    expect(screen.getByText('优先级 1')).toBeInTheDocument();
    expect(screen.getByText('优先级 2')).toBeInTheDocument();

    // New picks append to the tail instead of re-sorting to catalog order.
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]);
    expect(onChange).toHaveBeenCalledWith(['c', 'a', 'b']);
  });

  it('deselecting in ordered mode removes the value while keeping the rest in order', () => {
    const onChange = vi.fn();
    render(<MultiSelectDropdown options={options} selected={['c', 'a', 'b']} onChange={onChange} ordered />);

    fireEvent.click(screen.getByRole('button', { name: /已选/ }));
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]); // deselect a
    expect(onChange).toHaveBeenCalledWith(['c', 'b']);
  });

  it('shows a search box past the threshold and filters by label or value', () => {
    const many = ['a', 'b', 'c', 'd', 'e', 'f'].map((value) => ({
      value,
      label: `L-${value.toUpperCase()}`,
    }));
    render(<MultiSelectDropdown options={many} selected={[]} onChange={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /已选/ }));
    const search = screen.getByLabelText('搜索选项');
    const listbox = screen.getByRole('listbox');

    fireEvent.change(search, { target: { value: 'l-f' } });
    expect(within(listbox).getAllByRole('option')).toHaveLength(1);
    expect(within(listbox).getByText('L-F')).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'zzz' } });
    expect(within(listbox).queryAllByRole('option')).toHaveLength(0);
    expect(within(listbox).getByText('无匹配选项')).toBeInTheDocument();
  });

  it('keeps the popup open across a transient disabled flip (settings autosave)', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <MultiSelectDropdown options={options} selected={['a']} onChange={onChange} />,
    );

    fireEvent.click(screen.getByRole('button', { name: /已选/ }));
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    // Settings autosave briefly disables every field after each change; the
    // popup must survive the flip so multi-picking is not one-click-per-open.
    rerender(<MultiSelectDropdown options={options} selected={['a']} onChange={onChange} disabled />);
    const listbox = screen.getByRole('listbox');
    within(listbox).getAllByRole('checkbox').forEach((checkbox) => expect(checkbox).toBeDisabled());

    rerender(<MultiSelectDropdown options={options} selected={['a']} onChange={onChange} />);
    fireEvent.click(within(screen.getByRole('listbox')).getAllByRole('checkbox')[1]);
    expect(onChange).toHaveBeenCalledWith(['a', 'b']);
  });

  it('closes on Escape and restores focus to the trigger', () => {
    render(<MultiSelectDropdown options={options} selected={[]} onChange={vi.fn()} />);

    const trigger = screen.getByRole('button', { name: /已选/ });
    fireEvent.click(trigger);
    const listbox = screen.getByRole('listbox');
    fireEvent.keyDown(within(listbox).getAllByRole('checkbox')[0], { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
