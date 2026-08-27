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
    const openPanel = document.getElementById(
      screen.getByRole('button', { name: 'Search sources' }).getAttribute('aria-controls')!,
    );
    expect(openPanel).not.toHaveAttribute('inert');
    expect(openPanel).not.toHaveAttribute('hidden');
  });

  it('keeps description and trailing visible while collapsed without changing the accessible name', () => {
    render(
      <Collapsible
        title="Search sources"
        description="Optional subtitle"
        trailing={<span>3 ready</span>}
        defaultOpen={false}
      >
        <p>Hidden field</p>
      </Collapsible>,
    );

    const toggle = screen.getByRole('button', { name: 'Search sources' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveAttribute('aria-label', 'Search sources');
    expect(screen.getByText('Optional subtitle')).toBeVisible();
    expect(screen.getByText('3 ready')).toBeVisible();
    expect(screen.getByText('Hidden field')).not.toBeVisible();
  });

  it('marks collapsed content hidden and inert so fields are not keyboard or find-in-page reachable', () => {
    render(
      <Collapsible title="Search sources" defaultOpen={false}>
        <input aria-label="Hidden field" />
      </Collapsible>,
    );

    const toggle = screen.getByRole('button', { name: 'Search sources' });
    const panel = document.getElementById(toggle.getAttribute('aria-controls')!);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(panel).toHaveAttribute('inert');
    expect(panel).toHaveAttribute('hidden');
  });
});
