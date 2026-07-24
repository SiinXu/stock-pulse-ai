// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect } from 'react';

function isEditingSurface(element: Element | null): boolean {
  return Boolean(element?.closest('input, textarea, select, [contenteditable="true"], [role="dialog"]'));
}

export function useCommandPaletteShortcut(onOpen: () => void, enabled = true): void {
  useEffect(() => {
    if (!enabled) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        event.key.toLowerCase() !== 'k'
        || (!event.metaKey && !event.ctrlKey)
        || event.altKey
        || event.shiftKey
        || isEditingSurface(document.activeElement)
      ) {
        return;
      }
      event.preventDefault();
      onOpen();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [enabled, onOpen]);
}
