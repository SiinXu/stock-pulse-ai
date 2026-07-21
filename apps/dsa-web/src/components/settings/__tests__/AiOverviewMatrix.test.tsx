// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
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

  it('preserves settings framing and stable task-row identities through DataTable', () => {
    render(
      <AiOverviewMatrix
        getValue={(key) => key === 'LITELLM_MODEL' ? 'openai/gpt-test' : ''}
        language="en"
        availableRoutes={new Set(['openai/gpt-test'])}
      />,
    );

    const table = screen.getByRole('table', { name: 'Task routing overview' }) as HTMLTableElement;
    expect(table).toHaveClass('min-w-140', 'text-xs', 'border-inherit');
    expect(table.tHead).toHaveClass('border-inherit');
    expect(table.tBodies[0]).toHaveClass('divide-inherit');
    expect(table.parentElement).toHaveAttribute('data-data-table', 'ready');
    expect(table.parentElement?.parentElement).toHaveClass(
      'overflow-hidden',
      'border-[var(--settings-border)]',
    );
    expect(screen.getByTestId('ai-task-report')).toContainElement(
      screen.getByRole('rowheader', { name: 'Stock report' }),
    );
    expect(screen.getByTestId('ai-task-market_review')).toBeInTheDocument();
    expect(screen.getByTestId('ai-task-agent')).toBeInTheDocument();
    expect(screen.getByTestId('ai-task-vision')).toBeInTheDocument();
  });
});
