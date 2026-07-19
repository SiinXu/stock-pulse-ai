// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { CircleAlert, CircleCheck, Info, TriangleAlert, X } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { Button } from './Button';
import { IconButton } from './IconButton';
import { ToastViewport } from './ToastViewport';
import {
  ToastContext,
  type ToastContextValue,
  type ToastInput,
  type ToastTone,
} from './toastContext';

interface ToastRecord extends ToastInput {
  id: string;
  tone: ToastTone;
  durationMs: number;
}

interface ToastProviderProps {
  children: React.ReactNode;
  maxVisible?: number;
}

const DEFAULT_TOAST_DURATION_MS = 5000;
let toastSequence = 0;

const TOAST_TONE_STYLES: Record<ToastTone, string> = {
  info: 'border-info/25',
  success: 'border-success/25',
  warning: 'border-warning/25',
  danger: 'border-danger/25',
};

const TOAST_ICON_STYLES: Record<ToastTone, string> = {
  info: 'text-info',
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
};

const TOAST_ICONS = {
  info: Info,
  success: CircleCheck,
  warning: TriangleAlert,
  danger: CircleAlert,
} as const;

const ToastItem: React.FC<{
  toast: ToastRecord;
  closeLabel: string;
  onDismiss: (id: string) => void;
}> = ({ toast, closeLabel, onDismiss }) => {
  const Icon = TOAST_ICONS[toast.tone];

  useEffect(() => {
    if (toast.durationMs <= 0) return undefined;
    const timeout = window.setTimeout(() => onDismiss(toast.id), toast.durationMs);
    return () => window.clearTimeout(timeout);
  }, [onDismiss, toast.durationMs, toast.id]);

  return (
    <div
      role={toast.tone === 'danger' ? 'alert' : 'status'}
      aria-atomic="true"
      data-toast-id={toast.id}
      data-toast-tone={toast.tone}
      className={cn(
        'pointer-events-auto flex min-w-0 items-start gap-3 rounded-lg border bg-elevated p-3 text-foreground shadow-soft-card-strong',
        TOAST_TONE_STYLES[toast.tone],
      )}
    >
      <Icon className={cn('mt-1 h-4 w-4 shrink-0', TOAST_ICON_STYLES[toast.tone])} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground">{toast.title}</p>
        {toast.message ? <div className="mt-1 break-words text-sm text-secondary-text">{toast.message}</div> : null}
        {toast.action ? (
          <div className="mt-2">
            <Button
              type="button"
              variant="ghost"
              size="compact"
              onClick={() => {
                toast.action?.onClick();
                if (toast.action?.dismissOnClick !== false) onDismiss(toast.id);
              }}
            >
              {toast.action.label}
            </Button>
          </div>
        ) : null}
      </div>
      <IconButton
        type="button"
        variant="ghost"
        size="compact"
        aria-label={closeLabel}
        tooltip={false}
        onClick={() => onDismiss(toast.id)}
      >
        <X aria-hidden="true" />
      </IconButton>
    </div>
  );
};

export const ToastProvider: React.FC<ToastProviderProps> = ({ children, maxVisible = 4 }) => {
  const { t } = useUiLanguage();
  const [toasts, setToasts] = useState<ToastRecord[]>([]);

  const dismissToast = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);
  const clearToasts = useCallback(() => setToasts([]), []);
  const showToast = useCallback((input: ToastInput) => {
    toastSequence += 1;
    const id = `toast-${toastSequence}`;
    const record: ToastRecord = {
      ...input,
      id,
      tone: input.tone ?? 'info',
      durationMs: input.durationMs ?? DEFAULT_TOAST_DURATION_MS,
    };
    setToasts((current) => [...current, record].slice(-Math.max(1, maxVisible)));
    return id;
  }, [maxVisible]);

  const value = useMemo<ToastContextValue>(() => ({
    showToast,
    dismissToast,
    clearToasts,
  }), [clearToasts, dismissToast, showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport>
        {toasts.map((toast) => (
          <ToastItem
            key={toast.id}
            toast={toast}
            closeLabel={t('common.close')}
            onDismiss={dismissToast}
          />
        ))}
      </ToastViewport>
    </ToastContext.Provider>
  );
};
