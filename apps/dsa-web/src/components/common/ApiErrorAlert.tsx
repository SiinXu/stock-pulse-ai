// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
<<<<<<< HEAD
import {
  localizeParsedApiError,
  resolveErrorRemediation,
  type ParsedApiError,
} from '../../api/error';
=======
import { useContext, useEffect, useRef } from 'react';
import { localizeParsedApiError, type ParsedApiError } from '../../api/error';
>>>>>>> origin/main
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
<<<<<<< HEAD
  const remediation = resolveErrorRemediation(localizedError, language);
  const showDetails = localizedError.rawMessage.trim() && localizedError.rawMessage.trim() !== localizedError.message.trim();

  const resolvedActionLabel = actionLabel ?? remediation?.actionLabel;
  const remediationHref = !onAction ? remediation?.href : undefined;
  const resolvedOnAction = onAction ?? (
    remediationHref
      ? () => {
          // Avoid useNavigate so ApiErrorAlert remains usable outside a Router
          // (unit tests, isolated panels). Deep links still resolve correctly.
          window.location.assign(remediationHref);
        }
      : undefined
  );

  const action = resolvedActionLabel && resolvedOnAction ? (
    <Button type="button" variant="danger-subtle" size="compact" onClick={resolvedOnAction}>
      {resolvedActionLabel}
    </Button>
  ) : undefined;
  const content = (
    <>
      <p>{localizedError.message}</p>
      {remediation?.hint ? (
        <p className="mt-2 text-sm leading-5 text-[hsl(var(--color-danger-alert-text))] opacity-90">
          {remediation.hint}
        </p>
      ) : null}
      {showDetails ? (
        <details className="mt-3 rounded-lg border border-subtle bg-surface-2 px-3 py-2">
          <summary className="flex min-h-11 cursor-pointer items-center text-xs text-[hsl(var(--color-danger-alert-text))] opacity-90">{t('common.details')}</summary>
          <pre className="mt-2 whitespace-pre-wrap break-words text-xs leading-5 text-[hsl(var(--color-danger-alert-text))] opacity-85">
            {localizedError.rawMessage}
          </pre>
        </details>
      ) : null}
    </>
  );
  return onDismiss ? (
    <Alert
      tone="danger"
      urgent
      title={localizedError.title}
      className={className}
      action={action}
      dismissLabel={dismissLabel ?? t('common.close')}
      onDismiss={onDismiss}
    >
      {content}
    </Alert>
=======
  const onActionRef = useRef(onAction);
  const onDismissRef = useRef(onDismiss);
  const hasAction = Boolean(actionLabel && onAction);
  const hasDismiss = Boolean(onDismiss);

  useEffect(() => {
    onActionRef.current = onAction;
  }, [onAction]);

  useEffect(() => {
    onDismissRef.current = onDismiss;
  }, [onDismiss]);

  useEffect(() => {
    const toastId = showToast({
      title: localizedError.title,
      message: localizedError.message,
      tone: 'danger',
      durationMs: 0,
      closeLabel: dismissLabel ?? t('common.close'),
      action: hasAction ? {
        label: actionLabel as string,
        onClick: () => onActionRef.current?.(),
        dismissOnClick: false,
      } : undefined,
      onDismiss: hasDismiss ? () => onDismissRef.current?.() : undefined,
    });

    return () => dismissToast(toastId);
  }, [
    actionLabel,
    dismissLabel,
    dismissToast,
    hasAction,
    hasDismiss,
    localizedError.message,
    localizedError.title,
    showToast,
    t,
  ]);

  return null;
};

export const ApiErrorAlert: React.FC<ApiErrorAlertProps> = (props) => {
  const toastContext = useContext(ToastContext);
  return toastContext ? (
    <ApiErrorToast {...props} />
>>>>>>> origin/main
  ) : (
    <ToastProvider>
      <ApiErrorToast {...props} />
    </ToastProvider>
  );
};
