// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useCommandPaletteShortcut } from '../useCommandPaletteShortcut';

function ShortcutHarness({ onOpen }: { onOpen: () => void }) {
  useCommandPaletteShortcut(onOpen);
  return (
    <>
      <button type="button">Workspace</button>
      <input aria-label="Stock input" />
      <div role="dialog" aria-label="Existing dialog">
        <button type="button">Dialog action</button>
      </div>
    </>
  );
}

describe('useCommandPaletteShortcut', () => {
  it('opens on Cmd/Ctrl+K outside editing surfaces and ignores guarded focus', () => {
    const onOpen = vi.fn();
    render(<ShortcutHarness onOpen={onOpen} />);

    screen.getByRole('button', { name: 'Workspace' }).focus();
    fireEvent.keyDown(document, { key: 'k', metaKey: true });
    fireEvent.keyDown(document, { key: 'K', ctrlKey: true });
    expect(onOpen).toHaveBeenCalledTimes(2);

    screen.getByRole('textbox', { name: 'Stock input' }).focus();
    fireEvent.keyDown(document, { key: 'k', metaKey: true });

    screen.getByRole('button', { name: 'Dialog action' }).focus();
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true });
    expect(onOpen).toHaveBeenCalledTimes(2);
  });
});
