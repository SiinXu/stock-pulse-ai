// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useContext, useEffect, useMemo, useRef } from 'react';
import {
  localizeParsedApiError,
  resolveErrorRemediation,
  type ParsedApiError,
} from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { ToastProvider } from './ToastProvider';
import { ToastContext, useToast } from './toastContext';

interface ApiErrorAlertProps {
  error: ParsedApiError;
  className?: string;
  actionLabel?: string;
  onAction?: () => void;
  dismissLabel?: string;
  onDismiss?: () => void;
}

const ApiErrorToast: React.FC<ApiErrorAlertProps> = ({
  error,
  actionLabel,
  onAction,
  dismissLabel,
  onDismiss,
}) => {
  const { language, t } = useUiLanguage();
  const { showToast, dismissToast } = useToast();
  const localizedError = localizeParsedApiError(error, language);
  const remediation = resolveErrorRemediation(localizedError, language);
  const hasRemediation = remediation !== null;
  const remediationHref = remediation?.href;
  const resolvedActionLabel = actionLabel && onAction
    ? actionLabel
    : !actionLabel && onAction && remediation
      ? remediation.actionLabel
      : !actionLabel && !onAction && remediationHref
      ? remediation.actionLabel
      : undefined;
  const resolvedOnAction = useMemo(() => {
    if (actionLabel && onAction) return onAction;
    if (!actionLabel && onAction && hasRemediation) return onAction;
    if (!actionLabel && !onAction && remediationHref) {
      return () => window.location.assign(remediationHref);
    }
    return undefined;
  }, [actionLabel, hasRemediation, onAction, remediationHref]);
  const onActionRef = useRef(resolvedOnAction);
  const onDismissRef = useRef(onDismiss);
  const hasAction = Boolean(resolvedActionLabel && resolvedOnAction);
  const hasDismiss = Boolean(onDismiss);

  useEffect(() => {
    onActionRef.current = resolvedOnAction;
  }, [resolvedOnAction]);

  useEffect(() => {
    onDismissRef.current = onDismiss;
  }, [onDismiss]);

  useEffect(() => {
    const toastId = showToast({
      title: localizedError.title,
      message: (
        <>
          <p>{localizedError.message}</p>
          {remediation?.hint ? <p className="mt-1">{remediation.hint}</p> : null}
        </>
      ),
      tone: 'danger',
      durationMs: 0,
      closeLabel: dismissLabel ?? t('common.close'),
      action: hasAction ? {
        label: resolvedActionLabel as string,
        onClick: () => onActionRef.current?.(),
        dismissOnClick: false,
      } : undefined,
      onDismiss: hasDismiss ? () => onDismissRef.current?.() : undefined,
    });

    return () => dismissToast(toastId);
  }, [
    dismissLabel,
    dismissToast,
    hasAction,
    hasDismiss,
    localizedError.message,
    localizedError.title,
    remediation?.hint,
    resolvedActionLabel,
    showToast,
    t,
  ]);

  return null;
};

export const ApiErrorAlert: React.FC<ApiErrorAlertProps> = (props) => {
  const toastContext = useContext(ToastContext);
  return toastContext ? (
    <ApiErrorToast {...props} />
  ) : (
    <ToastProvider>
      <ApiErrorToast {...props} />
    </ToastProvider>
  );
};
