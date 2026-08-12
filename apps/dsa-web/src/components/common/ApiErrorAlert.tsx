// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useContext, useEffect, useMemo, useRef } from 'react';
import {
  classifyParsedApiError,
  localizeParsedApiError,
  resolveErrorRemediation,
  type ParsedApiError,
  type TaxonomySeverity,
} from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { ToastProvider } from './ToastProvider';
import { ToastContext, useToast } from './toastContext';


function taxonomySeverityToToastTone(
  severity: TaxonomySeverity | string | undefined,
): 'info' | 'warning' | 'danger' {
  if (severity === 'info') return 'info';
  if (severity === 'warning') return 'warning';
  return 'danger';
}

interface ApiErrorAlertProps {
  error: ParsedApiError;
  className?: string;
  actionLabel?: string;
  /**
   * Operation-owned action handler. For retry-classified errors this must re-run
   * the real failed operation (not only clear the error). Catalog Retry CTAs are
   * suppressed unless this handler is provided.
   */
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
  const remediation = resolveErrorRemediation(localizedError, language, {
    onRetry: onAction,
  });
  const classification = classifyParsedApiError(localizedError);
  const toastTone = taxonomySeverityToToastTone(
    remediation?.severity ?? classification.severity,
  );
  const hasRemediation = remediation !== null;
  const remediationHref = remediation?.href;
  const remediationKind = remediation?.actionKind;
  const isRetryRemediation = remediationKind === 'retry';
  const isExternalDocs = remediationKind === 'docs'
    && Boolean(remediationHref && /^https?:\/\//i.test(remediationHref));
  const resolvedActionLabel = actionLabel && onAction
    ? actionLabel
    : !actionLabel && onAction && remediation && (isRetryRemediation || remediation.actionKind !== 'none')
      ? remediation.actionLabel
      : !actionLabel && !onAction && remediationHref && remediationKind !== 'retry'
      ? remediation.actionLabel
      : undefined;
  const resolvedOnAction = useMemo(() => {
    if (actionLabel && onAction) return onAction;
    if (isRetryRemediation && onAction) return onAction;
    if (!actionLabel && onAction && hasRemediation && !isRetryRemediation) return onAction;
    if (!actionLabel && !onAction && remediationHref && remediationKind !== 'retry') {
      if (isExternalDocs) {
        return () => {
          window.open(remediationHref, '_blank', 'noopener,noreferrer');
        };
      }
      return () => window.location.assign(remediationHref);
    }
    return undefined;
  }, [
    actionLabel,
    hasRemediation,
    isExternalDocs,
    isRetryRemediation,
    onAction,
    remediationHref,
    remediationKind,
  ]);
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
      tone: toastTone,
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
    toastTone,
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
