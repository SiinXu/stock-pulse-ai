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
  info: 'border-info/25 bg-info/10',
  success: 'border-success/25 bg-success/10',
  warning: 'border-warning/25 bg-warning/10',
  danger: 'border-danger/25 bg-danger/10',
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
  onDismiss: (toast: ToastRecord) => void;
}> = ({ toast, closeLabel, onDismiss }) => {
  const Icon = TOAST_ICONS[toast.tone];
  const [isHovered, setIsHovered] = useState(false);
  const [hasFocus, setHasFocus] = useState(false);
  const isTimerPaused = isHovered || hasFocus;

  useEffect(() => {
    if (toast.durationMs <= 0 || isTimerPaused) return undefined;
    const timeout = window.setTimeout(() => onDismiss(toast), toast.durationMs);
    return () => window.clearTimeout(timeout);
  }, [isTimerPaused, onDismiss, toast]);

  return (
    <div
      role={toast.tone === 'danger' ? 'alert' : 'status'}
      aria-atomic="true"
      data-toast-id={toast.id}
      data-toast-tone={toast.tone}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onFocusCapture={() => setHasFocus(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setHasFocus(false);
        }
      }}
      className={cn(
        'pointer-events-auto flex min-w-0 items-center gap-2.5 rounded-lg border px-3 py-2.5 text-foreground shadow-soft-card-strong',
        TOAST_TONE_STYLES[toast.tone],
      )}
    >
      <Icon className={cn('h-5 w-5 shrink-0', TOAST_ICON_STYLES[toast.tone])} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground">{toast.title}</p>
        {toast.message ? <div className="mt-0.5 break-words text-xs leading-4 text-secondary-text">{toast.message}</div> : null}
      </div>
      {toast.action ? (
        <Button
          type="button"
          variant="ghost"
          size="default"
          className="shrink-0 bg-foreground/5 text-foreground hover:bg-foreground/10"
          onClick={() => {
            toast.action?.onClick();
            if (toast.action?.dismissOnClick !== false) onDismiss(toast);
          }}
        >
          {toast.action.label}
        </Button>
      ) : null}
      <IconButton
        type="button"
        variant="ghost"
        size="compact"
        aria-label={toast.closeLabel ?? closeLabel}
        tooltip={false}
        className="shrink-0"
        onClick={() => onDismiss(toast)}
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
  const handleToastDismiss = useCallback((toast: ToastRecord) => {
    dismissToast(toast.id);
    toast.onDismiss?.();
  }, [dismissToast]);
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
            onDismiss={handleToastDismiss}
          />
        ))}
      </ToastViewport>
    </ToastContext.Provider>
  );
};
