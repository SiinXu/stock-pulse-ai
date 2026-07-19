// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AiOverviewMatrix } from '../AiOverviewMatrix';

describe('AiOverviewMatrix', () => {
  it('keeps the compact task-routing action on the shared touch-target contract', () => {
    const onEditRouting = vi.fn();

    render(
      <AiOverviewMatrix
        getValue={() => ''}
        language="en"
        onEditRouting={onEditRouting}
      />,
    );

    const editButton = screen.getByRole('button', { name: 'Edit task routing' });
    expect(editButton).toHaveClass('ui-touch-target', 'h-6', 'min-w-6');
    fireEvent.click(editButton);
    expect(onEditRouting).toHaveBeenCalledTimes(1);
  });
});
