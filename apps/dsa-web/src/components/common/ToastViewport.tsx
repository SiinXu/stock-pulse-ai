// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { createPortal } from 'react-dom';
import { getOverlayStyle } from './overlayZ';

interface ToastViewportProps {
  children: React.ReactNode;
}

/** A portalled live region that remains announced while a dialog is open. */
export const ToastViewport: React.FC<ToastViewportProps> = ({ children }) => {
  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      data-overlay-root="toast"
      data-overlay-preserve="true"
      aria-live="polite"
      aria-relevant="additions text"
      style={getOverlayStyle('toast')}
      className="pointer-events-none fixed inset-x-4 bottom-4 flex flex-col gap-3 sm:left-auto sm:w-90"
    >
      {children}
    </div>,
    document.body,
  );
};
