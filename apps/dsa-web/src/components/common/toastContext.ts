// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { createContext, useContext } from 'react';

export type ToastTone = 'info' | 'success' | 'warning' | 'danger';

export interface ToastAction {
  label: string;
  onClick: () => void;
  dismissOnClick?: boolean;
}

export interface ToastInput {
  title: string;
  message?: React.ReactNode;
  tone?: ToastTone;
  durationMs?: number;
  action?: ToastAction;
}

export interface ToastContextValue {
  showToast: (toast: ToastInput) => string;
  dismissToast: (id: string) => void;
  clearToasts: () => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return context;
}
