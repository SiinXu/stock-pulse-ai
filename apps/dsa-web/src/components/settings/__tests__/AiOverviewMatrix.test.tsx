import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AiOverviewMatrix } from '../AiOverviewMatrix';

describe('AiOverviewMatrix', () => {
  it('keeps the task-routing action on a 44px touch target', () => {
    const onEditRouting = vi.fn();

    render(
      <AiOverviewMatrix
        getValue={() => ''}
        language="en"
        onEditRouting={onEditRouting}
      />,
    );

    const editButton = screen.getByRole('button', { name: 'Edit task routing' });
    expect(editButton).toHaveClass('min-h-11', 'min-w-11');
    fireEvent.click(editButton);
    expect(onEditRouting).toHaveBeenCalledTimes(1);
  });
});
