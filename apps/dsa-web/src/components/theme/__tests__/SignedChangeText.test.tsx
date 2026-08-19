// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { applyPriceDirection } from '../themeRuntime';
import { SignedChangeText } from '../SignedChangeText';

function renderChange(value: number | null | undefined, market?: string | null) {
  return render(
    <SignedChangeText value={value} market={market} fallbackClassName="text-secondary">
      {value == null ? '--' : String(value)}
    </SignedChangeText>,
  );
}

describe('SignedChangeText', () => {
  afterEach(() => {
    cleanup();
    applyPriceDirection('cn', { persist: false });
  });

  it('paints gains red under the CN red_up preference and does not use status classes', () => {
    applyPriceDirection('cn', { persist: false });
    renderChange(12.5, 'cn');
    const node = screen.getByText('12.5');
    expect(node).toHaveStyle({ color: 'var(--price-red)' });
    expect(node).not.toHaveClass('text-success');
    expect(node).not.toHaveClass('text-danger');
  });

  it('paints gains green under the US green_up preference', () => {
    applyPriceDirection('us', { persist: false });
    renderChange(12.5, 'cn');
    expect(screen.getByText('12.5')).toHaveStyle({ color: 'var(--price-green)' });
    expect(screen.getByText('12.5')).not.toHaveClass('text-success');
  });

  it('paints losses with the inverse hue of the active preference', () => {
    applyPriceDirection('cn', { persist: false });
    const cn = renderChange(-4, 'hk');
    expect(screen.getByText('-4')).toHaveStyle({ color: 'var(--price-green)' });
    cn.unmount();

    applyPriceDirection('us', { persist: false });
    renderChange(-4, 'hk');
    expect(screen.getByText('-4')).toHaveStyle({ color: 'var(--price-red)' });
  });

  it('leaves zero and unknown values unpainted', () => {
    applyPriceDirection('us', { persist: false });
    const zero = renderChange(0, 'us');
    expect(screen.getByText('0')).not.toHaveStyle({ color: 'var(--price-red)' });
    expect(screen.getByText('0')).not.toHaveStyle({ color: 'var(--price-green)' });
    expect(screen.getByText('0')).toHaveClass('text-secondary');
    zero.unmount();

    renderChange(null, 'us');
    expect(screen.getByText('--')).not.toHaveStyle({ color: 'var(--price-red)' });
    expect(screen.getByText('--')).not.toHaveStyle({ color: 'var(--price-green)' });
    expect(screen.getByText('--')).toHaveClass('text-secondary');
  });

  it('leaves an unresolved market unpainted instead of inventing a cn convention', () => {
    applyPriceDirection('us', { persist: false });
    renderChange(1, '7203.T');
    const node = screen.getByText('1');
    expect(node).not.toHaveStyle({ color: 'var(--price-red)' });
    expect(node).not.toHaveStyle({ color: 'var(--price-green)' });
    expect(node).toHaveClass('text-secondary');

    cleanup();
    applyPriceDirection('cn', { persist: false });
    renderChange(-4, 'jp');
    const jpNode = screen.getByText('-4');
    expect(jpNode).not.toHaveStyle({ color: 'var(--price-red)' });
    expect(jpNode).not.toHaveStyle({ color: 'var(--price-green)' });
    expect(jpNode).toHaveClass('text-secondary');
  });

  it('still paints a non-instrument figure when market is omitted, using document preference', () => {
    applyPriceDirection('cn', { persist: false });
    renderChange(12.5);
    expect(screen.getByText('12.5')).toHaveStyle({ color: 'var(--price-red)' });
    cleanup();
    applyPriceDirection('us', { persist: false });
    renderChange(12.5);
    expect(screen.getByText('12.5')).toHaveStyle({ color: 'var(--price-green)' });
  });
});
