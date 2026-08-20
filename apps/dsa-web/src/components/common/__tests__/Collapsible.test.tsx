// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Collapsible } from '../Collapsible';

describe('Collapsible', () => {
  it('supports controlled open and keyboard-accessible disclosure', () => {
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <Collapsible title="Search sources" open={false} onOpenChange={onOpenChange}>
        <p>Hidden field</p>
      </Collapsible>,
    );

    const toggle = screen.getByRole('button', { name: 'Search sources' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveAttribute('aria-controls');
    fireEvent.click(toggle);
    expect(onOpenChange).toHaveBeenCalledWith(true);

    rerender(
      <Collapsible title="Search sources" open onOpenChange={onOpenChange}>
        <p>Hidden field</p>
      </Collapsible>,
    );
    expect(screen.getByRole('button', { name: 'Search sources' })).toHaveAttribute('aria-expanded', 'true');
  });
});
